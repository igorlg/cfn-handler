"""Unit tests for ``_internal/poller.py`` (CloudWatch Events provisioning)."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cfn_handler._internal.poller import (
    EVENT_MARKER_PERMISSION,
    EVENT_MARKER_POLL,
    EVENT_MARKER_RULE,
    PollingDependencyError,
    is_poll_event,
    setup_polling,
    teardown_polling,
)


def test_is_poll_event_true_when_marker_present() -> None:
    assert is_poll_event({EVENT_MARKER_POLL: True}) is True


def test_is_poll_event_false_for_initial_event() -> None:
    assert is_poll_event({"RequestType": "Create"}) is False


def test_polling_dependency_error_is_cfn_handler_error() -> None:
    """Subclass relationship lets users catch CfnHandlerError to handle this."""
    from cfn_handler.exceptions import CfnHandlerError

    assert issubclass(PollingDependencyError, CfnHandlerError)


def test_setup_polling_raises_when_boto3_missing(events: dict[str, dict[str, Any]]) -> None:
    """Issue: polling depends on boto3; absence must be a clear error."""
    with patch.dict(sys.modules, {"boto3": None}), pytest.raises(PollingDependencyError):
        setup_polling(events["Create"], function_name="test-fn")


def test_setup_polling_provisions_rule_target_and_permission(
    events: dict[str, dict[str, Any]],
) -> None:
    """Verify all three SDK calls happen and the event is mutated with markers."""
    fake_events = MagicMock()
    fake_events.put_rule.return_value = {"RuleArn": "arn:aws:events:us-east-1:123:rule/TestResourceXYZ12345"}
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        event = events["Create"]
        setup_polling(event, function_name="test-fn", polling_interval_minutes=2)

    fake_events.put_rule.assert_called_once()
    fake_lambda.add_permission.assert_called_once()
    fake_events.put_targets.assert_called_once()

    assert event[EVENT_MARKER_POLL] is True
    assert event[EVENT_MARKER_RULE] == "arn:aws:events:us-east-1:123:rule/TestResourceXYZ12345"
    assert EVENT_MARKER_PERMISSION in event


def test_setup_polling_uses_minute_singular_for_one(events: dict[str, dict[str, Any]]) -> None:
    """`rate(1 minute)` not `rate(1 minutes)` — CFN-EventBridge API quirk."""
    fake_events = MagicMock()
    fake_events.put_rule.return_value = {"RuleArn": "arn:aws:events:us-east-1:123:rule/r/x"}
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        setup_polling(events["Create"], function_name="test-fn", polling_interval_minutes=1)

    schedule = fake_events.put_rule.call_args.kwargs["ScheduleExpression"]
    assert schedule == "rate(1 minute)"


def test_teardown_polling_cleans_up_all_resources(
    events: dict[str, dict[str, Any]],
) -> None:
    """All three teardown SDK calls happen when markers are present."""
    event = events["Update"]
    event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRuleName"
    event[EVENT_MARKER_PERMISSION] = "MyPermSid"

    fake_events = MagicMock()
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        teardown_polling(event, function_name="test-fn")

    fake_events.remove_targets.assert_called_once_with(Rule="MyRuleName", Ids=["1"])
    fake_lambda.remove_permission.assert_called_once_with(FunctionName="test-fn", StatementId="MyPermSid")
    fake_events.delete_rule.assert_called_once_with(Name="MyRuleName")


def test_teardown_polling_skips_when_no_rule_marker(
    events: dict[str, dict[str, Any]],
) -> None:
    """Defensive: don't fail if the markers were never set (early-error path)."""
    event = events["Update"]  # no markers
    fake_events = MagicMock()
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        teardown_polling(event, function_name="test-fn")

    fake_events.remove_targets.assert_not_called()
    fake_events.delete_rule.assert_not_called()


def test_teardown_polling_swallows_remove_targets_failure(
    events: dict[str, dict[str, Any]],
) -> None:
    """Best-effort cleanup: a failing remove_targets must not block subsequent steps."""
    event = events["Update"]
    event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRule"
    event[EVENT_MARKER_PERMISSION] = "Sid"

    fake_events = MagicMock()
    fake_events.remove_targets.side_effect = RuntimeError("simulated SDK error")
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        teardown_polling(event, function_name="test-fn")

    # Permission removal and rule deletion still attempted.
    fake_lambda.remove_permission.assert_called_once()
    fake_events.delete_rule.assert_called_once()


def test_teardown_polling_swallows_remove_permission_failure(
    events: dict[str, dict[str, Any]],
) -> None:
    """A failing remove_permission must not block delete_rule."""
    event = events["Update"]
    event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRule"
    event[EVENT_MARKER_PERMISSION] = "Sid"

    fake_events = MagicMock()
    fake_lambda = MagicMock()
    fake_lambda.remove_permission.side_effect = RuntimeError("simulated")

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        teardown_polling(event, function_name="test-fn")

    fake_events.delete_rule.assert_called_once()


def test_teardown_polling_swallows_delete_rule_failure(
    events: dict[str, dict[str, Any]],
) -> None:
    """A failing delete_rule still completes the teardown cleanly."""
    event = events["Update"]
    event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRule"
    event[EVENT_MARKER_PERMISSION] = "Sid"

    fake_events = MagicMock()
    fake_events.delete_rule.side_effect = RuntimeError("simulated")
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        # Should not raise:
        teardown_polling(event, function_name="test-fn")


def test_teardown_polling_skips_permission_removal_when_no_sid(
    events: dict[str, dict[str, Any]],
) -> None:
    event = events["Update"]
    event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRule"
    # No EVENT_MARKER_PERMISSION present.

    fake_events = MagicMock()
    fake_lambda = MagicMock()

    with (
        patch("cfn_handler._internal.poller._events_client", return_value=fake_events),
        patch("cfn_handler._internal.poller._lambda_client", return_value=fake_lambda),
    ):
        teardown_polling(event, function_name="test-fn")

    fake_lambda.remove_permission.assert_not_called()
    fake_events.delete_rule.assert_called_once()
