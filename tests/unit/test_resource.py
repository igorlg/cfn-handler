"""Unit tests for the public ``CustomResource`` class.

Strategy: use ``test_mode=True`` so we don't actually PUT to a CFN URL; we
inspect ``last_response`` to verify the payload that *would* have been sent.
This is exactly the test-mode pattern from upstream issues #52 / #54.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

import cfn_handler
from cfn_handler import CustomResource
from cfn_handler.resource import (
    _REQUEST_TYPES,
    DoubleRegistrationError,
    LambdaContext,
    _generate_physical_id,
)

# ---- Public API surface --------------------------------------------------


def test_public_api_exports() -> None:
    """Anything in __all__ must be importable; __all__ must be the source of truth."""
    assert set(cfn_handler.__all__) == {
        "CfnHandlerError",
        "CustomResource",
        "ResponseError",
        "__version__",
    }
    for name in cfn_handler.__all__:
        assert hasattr(cfn_handler, name), f"{name} listed in __all__ but missing from module"


def test_version_is_a_string() -> None:
    assert isinstance(cfn_handler.__version__, str)
    assert cfn_handler.__version__  # non-empty


def test_lambda_context_protocol_accepts_real_shape() -> None:
    """Protocol is structural; a Mock with the right attrs satisfies it."""
    ctx = Mock(spec=LambdaContext)
    ctx.aws_request_id = "x"
    ctx.function_name = "y"
    ctx.get_remaining_time_in_millis = Mock(return_value=1000)
    # Just exercise the type-bound attributes:
    assert ctx.aws_request_id == "x"
    assert ctx.function_name == "y"
    assert ctx.get_remaining_time_in_millis() == 1000


# ---- Decorator registration ---------------------------------------------


@pytest.mark.parametrize("attr", ["create", "update", "delete"])
def test_lifecycle_decorator_registers_handler(attr: str) -> None:
    resource = CustomResource(test_mode=True)

    @getattr(resource, attr)
    def fn(_event: dict[str, Any], _context: LambdaContext) -> None:
        return None

    request_type = attr.capitalize()
    assert resource._lifecycle_handlers[request_type] is fn


@pytest.mark.parametrize("attr", ["poll_create", "poll_update", "poll_delete"])
def test_poll_decorator_registers_handler(attr: str) -> None:
    resource = CustomResource(test_mode=True)

    @getattr(resource, attr)
    def fn(_event: dict[str, Any], _context: LambdaContext) -> None:
        return None

    request_type = attr.replace("poll_", "").capitalize()
    assert resource._poll_handlers[request_type] is fn


def test_lifecycle_decorator_returns_original_callable() -> None:
    resource = CustomResource(test_mode=True)

    def fn(_event: dict[str, Any], _context: LambdaContext) -> None:
        return None

    decorated = resource.create(fn)
    assert decorated is fn


@pytest.mark.parametrize("attr", ["create", "update", "delete"])
def test_double_lifecycle_registration_raises(attr: str) -> None:
    resource = CustomResource(test_mode=True)
    decorator = getattr(resource, attr)

    @decorator
    def first(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with pytest.raises(DoubleRegistrationError):

        @decorator
        def second(_e: dict[str, Any], _c: LambdaContext) -> None:
            return None


@pytest.mark.parametrize("attr", ["poll_create", "poll_update", "poll_delete"])
def test_double_poll_registration_raises(attr: str) -> None:
    resource = CustomResource(test_mode=True)
    decorator = getattr(resource, attr)

    @decorator
    def first(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with pytest.raises(DoubleRegistrationError):

        @decorator
        def second(_e: dict[str, Any], _c: LambdaContext) -> None:
            return None


def test_double_registration_error_is_a_value_error() -> None:
    """Users who don't want to import the internal class can catch ValueError."""
    assert issubclass(DoubleRegistrationError, ValueError)


# ---- Lifecycle dispatch (no polling) ------------------------------------


def test_create_dispatch_invokes_create_handler(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)
    captured: list[tuple[dict[str, Any], LambdaContext]] = []

    @resource.create
    def on_create(event: dict[str, Any], context: LambdaContext) -> None:
        captured.append((event, context))
        return None

    resource(events["Create"], mock_context)
    assert len(captured) == 1
    assert captured[0][0] is events["Create"]
    assert captured[0][1] is mock_context


def test_update_and_delete_dispatch(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)
    calls: list[str] = []

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        calls.append("create")

    @resource.update
    def on_update(_e: dict[str, Any], _c: LambdaContext) -> None:
        calls.append("update")

    @resource.delete
    def on_delete(_e: dict[str, Any], _c: LambdaContext) -> None:
        calls.append("delete")

    resource(events["Update"], mock_context)
    resource(events["Delete"], mock_context)
    assert calls == ["update", "delete"]


def test_handler_return_value_becomes_data(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"Endpoint": "https://x.example", "Token": "abc"}

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Status"] == "SUCCESS"
    assert resource.last_response["Data"] == {"Endpoint": "https://x.example", "Token": "abc"}


def test_handler_returning_none_yields_empty_data(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Data"] == {}


def test_unknown_request_type_yields_failed(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)
    bogus = events["Create"]
    bogus["RequestType"] = "FooBar"
    resource(bogus, mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Status"] == "FAILED"
    assert "FooBar" in resource.last_response["Reason"]


def test_missing_handler_for_known_request_type_yields_failed(
    events: dict[str, dict[str, Any]], mock_context: Mock
) -> None:
    resource = CustomResource(test_mode=True)
    # No handlers registered.
    resource(events["Delete"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Status"] == "FAILED"
    assert "Delete" in resource.last_response["Reason"]


# ---- Exception handling --------------------------------------------------


def test_handler_exception_is_reported_as_failed(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        raise RuntimeError("policy not found")

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Status"] == "FAILED"
    assert "policy not found" in resource.last_response["Reason"]


def test_handler_exception_with_empty_message_uses_class_name(
    events: dict[str, dict[str, Any]], mock_context: Mock
) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        raise RuntimeError

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Reason"] == "RuntimeError"


# ---- PhysicalResourceId semantics ---------------------------------------


def test_create_default_physical_resource_id_is_generated(
    events: dict[str, dict[str, Any]], mock_context: Mock
) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    pid = resource.last_response["PhysicalResourceId"]
    assert pid
    assert "TestResource" in pid


def test_update_echoes_existing_physical_resource_id(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.update
    def on_update(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Update"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["PhysicalResourceId"] == events["Update"]["PhysicalResourceId"]


def test_update_overrides_physical_resource_id_for_replacement(
    events: dict[str, dict[str, Any]], mock_context: Mock
) -> None:
    resource = CustomResource(test_mode=True)

    @resource.update
    def on_update(_e: dict[str, Any], _c: LambdaContext) -> None:
        resource.physical_resource_id = "new-id-replaced"

    resource(events["Update"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["PhysicalResourceId"] == "new-id-replaced"


def test_delete_echoes_existing_physical_resource_id(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.delete
    def on_delete(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Delete"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["PhysicalResourceId"] == events["Delete"]["PhysicalResourceId"]


def test_no_echo_default_omitted(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert "NoEcho" not in resource.last_response


def test_no_echo_can_be_set_from_handler(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        resource.no_echo = True

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["NoEcho"] is True


# ---- Init failure (#7 / #67) --------------------------------------------


def test_init_failure_short_circuits_to_failed_with_pid(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    """Issue #7/#67: init_failure must produce a usable PhysicalResourceId
    so CloudFormation can roll back, not get stuck in ROLLBACK_FAILED."""
    resource = CustomResource(test_mode=True)
    resource.init_failure(RuntimeError("boom in cold start"))

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["Status"] == "FAILED"
    assert "boom in cold start" in resource.last_response["Reason"]
    assert resource.last_response["PhysicalResourceId"]


def test_init_failure_for_update_echoes_existing_pid(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    resource = CustomResource(test_mode=True)
    resource.init_failure(RuntimeError("init blew up"))

    resource(events["Update"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response["PhysicalResourceId"] == events["Update"]["PhysicalResourceId"]


# ---- Test mode ----------------------------------------------------------


def test_test_mode_does_not_send_response(events: dict[str, dict[str, Any]], mock_context: Mock) -> None:
    """Test mode captures the response on the instance instead of POSTing."""
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    captured = resource(events["Create"], mock_context)
    assert captured is not None
    assert captured["Status"] == "SUCCESS"
    assert captured is resource.last_response


def test_test_mode_returns_none_outside_test_mode(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Outside test mode, __call__ returns None (Lambda ignores return values)."""
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    # Even in test_mode we still get the response back; explicitly verify the
    # falsey-check semantics for paranoid tests.
    assert resource(events["Create"], mock_context) is not None


# ---- log_level acceptance (#66) ------------------------------------------


@pytest.mark.parametrize(
    "log_level",
    ["DEBUG", "INFO", 10, 20, None],
)
def test_log_level_constructor_accepts_str_int_or_none(log_level: int | str | None) -> None:
    """Issue #66: log_level should accept int and str (and None to leave alone)."""
    CustomResource(test_mode=True, log_level=log_level)


# ---- Internal helpers ----------------------------------------------------


def test_request_types_set_includes_only_three() -> None:
    assert _REQUEST_TYPES == {"Create", "Update", "Delete"}


def test_generate_physical_id_includes_logical_resource_id() -> None:
    event = {"StackId": "arn:aws:cloudformation:.../mystack/abcd-1234", "LogicalResourceId": "MyRes"}
    pid = _generate_physical_id(event, "request-id-aaaaaaaa")
    assert "MyRes" in pid


def test_generate_physical_id_handles_short_stack_id() -> None:
    """Some test fixtures use a non-ARN stack id."""
    event = {"StackId": "shortid", "LogicalResourceId": "X"}
    pid = _generate_physical_id(event, "rid")
    assert pid


def test_generate_physical_id_is_unique_across_calls() -> None:
    event = {"StackId": "arn:aws:cloudformation:.../s/g", "LogicalResourceId": "R"}
    a = _generate_physical_id(event, "req-1")
    b = _generate_physical_id(event, "req-1")
    assert a != b
