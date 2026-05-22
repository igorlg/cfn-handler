"""Event factory: build canonical CloudFormation custom-resource event dicts.

Defaults use safe placeholder values: the response URL host is
``example.invalid`` (RFC 6761 reserved name guaranteed not to resolve)
and the account ID is ``111111111111`` (AWS-reserved example account),
so a misrouted test cannot hit real infrastructure.
"""

from __future__ import annotations

from typing import Any, Literal

#: The set of valid CloudFormation custom-resource request types.
RequestType = Literal["Create", "Update", "Delete"]

_DEFAULT_STACK_ID = (
    "arn:aws:cloudformation:us-east-1:111111111111:stack/test-stack/00000000-0000-0000-0000-000000000000"
)
_DEFAULT_REQUEST_ID = "00000000-0000-0000-0000-000000000000"
_DEFAULT_LOGICAL_ID = "TestResource"
_DEFAULT_RESOURCE_TYPE = "Custom::Test"
_DEFAULT_RESPONSE_URL = "https://example.invalid/cfn-response"
_DEFAULT_SERVICE_TOKEN = "arn:aws:lambda:us-east-1:111111111111:function:test-function"


def make_event(
    request_type: RequestType = "Create",
    *,
    stack_id: str = _DEFAULT_STACK_ID,
    request_id: str = _DEFAULT_REQUEST_ID,
    logical_resource_id: str = _DEFAULT_LOGICAL_ID,
    physical_resource_id: str | None = None,
    resource_type: str = _DEFAULT_RESOURCE_TYPE,
    resource_properties: dict[str, Any] | None = None,
    old_resource_properties: dict[str, Any] | None = None,
    response_url: str = _DEFAULT_RESPONSE_URL,
    service_token: str = _DEFAULT_SERVICE_TOKEN,
) -> dict[str, Any]:
    """Build a CloudFormation custom-resource event dict.

    Args:
        request_type: ``"Create"``, ``"Update"``, or ``"Delete"``.
        stack_id: Full stack ARN.
        request_id: Per-invocation UUID.
        logical_resource_id: Template-side logical name of the resource.
        physical_resource_id: Required for Update/Delete; raises
            ``ValueError`` if missing.
        resource_type: ``Custom::*`` type from the template.
        resource_properties: ``ResourceProperties`` dict; defaults to ``{}``.
        old_resource_properties: ``OldResourceProperties`` dict for Update;
            defaults to ``{}`` for Update events, omitted otherwise.
        response_url: The presigned URL CFN expects the response on.
        service_token: ARN of the Lambda function backing this custom
            resource.

    Returns:
        A dict matching the documented CFN custom-resource event shape.

    Raises:
        ValueError: For Update/Delete events when ``physical_resource_id``
            is not supplied.
    """
    if request_type in ("Update", "Delete") and physical_resource_id is None:
        msg = (
            f"physical_resource_id is required for {request_type} events; "
            "real CFN events always carry one. Pass it explicitly."
        )
        raise ValueError(msg)

    event: dict[str, Any] = {
        "RequestType": request_type,
        "ServiceToken": service_token,
        "ResponseURL": response_url,
        "StackId": stack_id,
        "RequestId": request_id,
        "LogicalResourceId": logical_resource_id,
        "ResourceType": resource_type,
        "ResourceProperties": resource_properties if resource_properties is not None else {},
    }
    if physical_resource_id is not None:
        event["PhysicalResourceId"] = physical_resource_id
    if request_type == "Update":
        event["OldResourceProperties"] = old_resource_properties if old_resource_properties is not None else {}
    return event
