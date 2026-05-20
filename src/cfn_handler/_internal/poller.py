"""Polling support: provision and tear down the CloudWatch Events re-invocation.

For long-running custom resources, the user signals "not done" by registering
a poll handler. The lifecycle handler runs once, kicks off the work, and
returns. We then provision a CloudWatch Events rule that re-invokes the same
Lambda on a fixed cadence; on each re-invocation we route to the poll
handler. When the poller signals completion we tear down the rule.

This module lazy-imports ``boto3`` so the rest of the library has zero
runtime dependencies. ``boto3`` is preinstalled in AWS Lambda Python
runtimes; we only need it when polling is actually used.
"""

from __future__ import annotations

import json
import secrets
import string
from typing import TYPE_CHECKING, Any

from cfn_handler._internal.log import logger
from cfn_handler.exceptions import CfnHandlerError

if TYPE_CHECKING:
    from mypy_boto3_events.client import EventBridgeClient
    from mypy_boto3_lambda.client import LambdaClient

#: Markers we add to the event payload to identify a poll re-invocation.
EVENT_MARKER_POLL = "CfnHandlerPoll"
EVENT_MARKER_RULE = "CfnHandlerRule"
EVENT_MARKER_PERMISSION = "CfnHandlerPermission"
EVENT_MARKER_DATA = "CfnHandlerData"


class PollingDependencyError(CfnHandlerError):
    """Polling was requested but ``boto3`` is not importable.

    ``boto3`` ships preinstalled in AWS Lambda Python runtimes; this error
    only triggers in environments where the library is loaded outside Lambda
    without the optional dependency.
    """


def is_poll_event(event: dict[str, Any]) -> bool:
    """Return True when ``event`` is a polling re-invocation, not a CFN event."""
    return EVENT_MARKER_POLL in event


def _ensure_boto3() -> Any:
    """Lazy-import boto3, raising :class:`PollingDependencyError` if unavailable."""
    try:
        import boto3
    except ImportError as cause:
        raise PollingDependencyError(
            "Polling support requires `boto3`, which is preinstalled in AWS "
            "Lambda Python runtimes. Install it explicitly for local testing: "
            "`uv add boto3`."
        ) from cause
    return boto3


def _rand_suffix(length: int = 8) -> str:
    """Generate a short random suffix for resource naming uniqueness."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _events_client(region: str | None) -> EventBridgeClient:
    boto3 = _ensure_boto3()
    client: EventBridgeClient = boto3.client("events", region_name=region)
    return client


def _lambda_client(region: str | None) -> LambdaClient:
    boto3 = _ensure_boto3()
    client: LambdaClient = boto3.client("lambda", region_name=region)
    return client


def setup_polling(
    event: dict[str, Any],
    function_name: str,
    polling_interval_minutes: int = 1,
    region: str | None = None,
) -> None:
    """Provision the CloudWatch Events rule that will re-invoke the Lambda.

    Mutates ``event`` in place to add the marker keys read on re-invocation.

    Raises:
        PollingDependencyError: If ``boto3`` is not importable.
    """
    events = _events_client(region)
    lam = _lambda_client(region)

    schedule_unit = "minute" if polling_interval_minutes == 1 else "minutes"
    rule_name = f"{event['LogicalResourceId']}{_rand_suffix()}"

    rule = events.put_rule(
        Name=rule_name,
        ScheduleExpression=f"rate({polling_interval_minutes} {schedule_unit})",
        State="ENABLED",
    )
    rule_arn = rule["RuleArn"]

    statement_id = f"{event['LogicalResourceId']}{_rand_suffix()}"
    lam.add_permission(
        FunctionName=function_name,
        StatementId=statement_id,
        Action="lambda:InvokeFunction",
        Principal="events.amazonaws.com",
        SourceArn=rule_arn,
    )

    # Mark the event so the next invocation knows to dispatch to the poll handler.
    event[EVENT_MARKER_POLL] = True
    event[EVENT_MARKER_RULE] = rule_arn
    event[EVENT_MARKER_PERMISSION] = statement_id

    arn_parts = rule_arn.split(":")
    partition, region_part, account_id = arn_parts[1], arn_parts[3], arn_parts[4]
    target_arn = f"arn:{partition}:lambda:{region_part}:{account_id}:function:{function_name}"
    events.put_targets(
        Rule=rule_name,
        Targets=[
            {
                "Id": "1",
                "Arn": target_arn,
                "Input": json.dumps(event),
            }
        ],
    )
    logger.info("Polling enabled: rule=%s target=%s", rule_name, target_arn)


def teardown_polling(
    event: dict[str, Any],
    function_name: str,
    region: str | None = None,
) -> None:
    """Remove the CloudWatch Events rule, target, and Lambda permission.

    Best-effort: failures to remove are logged at ERROR but not raised, so
    a successful CFN response is not blocked by orphan-resource cleanup.
    """
    rule_arn: str | None = event.get(EVENT_MARKER_RULE)
    permission_sid: str | None = event.get(EVENT_MARKER_PERMISSION)

    if rule_arn is None:
        logger.warning("teardown_polling: no %s in event; skipping rule cleanup", EVENT_MARKER_RULE)
        return

    rule_name = rule_arn.split("/")[1]
    events = _events_client(region)
    lam = _lambda_client(region)

    try:
        events.remove_targets(Rule=rule_name, Ids=["1"])
    except Exception:
        logger.exception("teardown_polling: remove_targets failed for rule %s", rule_name)

    if permission_sid is not None:
        try:
            lam.remove_permission(FunctionName=function_name, StatementId=permission_sid)
        except Exception:
            logger.exception("teardown_polling: remove_permission failed for sid %s", permission_sid)

    try:
        events.delete_rule(Name=rule_name)
    except Exception:
        logger.exception("teardown_polling: delete_rule failed for rule %s", rule_name)

    logger.info("Polling teardown complete for rule=%s", rule_name)
