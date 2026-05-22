"""Tests for ``cfn_handler.testing.make_event`` and ``make_context``."""

from __future__ import annotations

import pytest

from cfn_handler.resource import LambdaContext
from cfn_handler.testing import make_context, make_event

# ---- make_event --------------------------------------------------------


def test_default_create_event_is_well_formed() -> None:
    event = make_event()
    assert event["RequestType"] == "Create"
    for key in (
        "ServiceToken",
        "ResponseURL",
        "StackId",
        "RequestId",
        "LogicalResourceId",
        "ResourceType",
        "ResourceProperties",
    ):
        assert key in event, f"missing {key}"
    assert "PhysicalResourceId" not in event  # not present on Create
    assert "OldResourceProperties" not in event  # only on Update


def test_update_event_requires_physical_resource_id() -> None:
    with pytest.raises(ValueError, match="physical_resource_id"):
        make_event(request_type="Update")


def test_delete_event_requires_physical_resource_id() -> None:
    with pytest.raises(ValueError, match="physical_resource_id"):
        make_event(request_type="Delete")


def test_update_event_with_physical_resource_id_is_well_formed() -> None:
    event = make_event(request_type="Update", physical_resource_id="abc-123")
    assert event["RequestType"] == "Update"
    assert event["PhysicalResourceId"] == "abc-123"
    assert event["OldResourceProperties"] == {}  # default empty dict on Update


def test_delete_event_with_physical_resource_id_is_well_formed() -> None:
    event = make_event(request_type="Delete", physical_resource_id="abc-123")
    assert event["RequestType"] == "Delete"
    assert event["PhysicalResourceId"] == "abc-123"
    assert "OldResourceProperties" not in event


def test_resource_properties_override_is_applied() -> None:
    event = make_event(resource_properties={"Foo": "bar"})
    assert event["ResourceProperties"] == {"Foo": "bar"}


def test_old_resource_properties_override_is_applied_for_update() -> None:
    event = make_event(
        request_type="Update",
        physical_resource_id="x",
        old_resource_properties={"Old": True},
    )
    assert event["OldResourceProperties"] == {"Old": True}


def test_defaults_use_safe_placeholders() -> None:
    event = make_event()
    # RFC 6761 reserved name: example.invalid is guaranteed not to resolve.
    assert "example.invalid" in event["ResponseURL"]
    # AWS-reserved example account IDs.
    assert "111111111111" in event["StackId"]
    assert "111111111111" in event["ServiceToken"]


def test_field_overrides_propagate_individually() -> None:
    event = make_event(
        stack_id="arn:aws:cloudformation:us-west-2:222222222222:stack/x/y",
        request_id="custom-uuid",
        logical_resource_id="MyLogical",
        resource_type="Custom::Banana",
        response_url="https://other.invalid/cfn",
        service_token="arn:aws:lambda:us-west-2:222222222222:function:x",
    )
    assert event["StackId"] == "arn:aws:cloudformation:us-west-2:222222222222:stack/x/y"
    assert event["RequestId"] == "custom-uuid"
    assert event["LogicalResourceId"] == "MyLogical"
    assert event["ResourceType"] == "Custom::Banana"
    assert event["ResponseURL"] == "https://other.invalid/cfn"
    assert event["ServiceToken"] == "arn:aws:lambda:us-west-2:222222222222:function:x"


# ---- make_context ------------------------------------------------------


def test_make_context_satisfies_lambda_context_protocol() -> None:
    """The factory's return value must structurally satisfy LambdaContext."""

    def consume(ctx: LambdaContext) -> int:
        return ctx.get_remaining_time_in_millis()

    ctx = make_context()
    assert consume(ctx) > 0
    assert isinstance(ctx.aws_request_id, str)
    assert isinstance(ctx.function_name, str)


def test_make_context_remaining_time_override() -> None:
    ctx = make_context(remaining_time_ms=5_000)
    assert ctx.get_remaining_time_in_millis() == 5_000


def test_make_context_default_remaining_time_is_positive() -> None:
    ctx = make_context()
    assert ctx.get_remaining_time_in_millis() > 0


def test_make_context_field_overrides() -> None:
    ctx = make_context(
        aws_request_id="custom-id",
        function_name="my-func",
        invoked_function_arn="arn:aws:lambda:us-east-1:123:function:my-func",
        log_group_name="/aws/lambda/my-func",
        log_stream_name="2026/05/22/[$LATEST]xyz",
    )
    assert ctx.aws_request_id == "custom-id"
    assert ctx.function_name == "my-func"
    assert ctx.invoked_function_arn == "arn:aws:lambda:us-east-1:123:function:my-func"
    assert ctx.log_group_name == "/aws/lambda/my-func"
    assert ctx.log_stream_name == "2026/05/22/[$LATEST]xyz"


def test_make_context_each_call_returns_independent_instance() -> None:
    """Mutations to one context don't bleed into others."""
    ctx_a = make_context()
    ctx_b = make_context()
    ctx_a.aws_request_id = "mutated"
    assert ctx_b.aws_request_id != "mutated"
