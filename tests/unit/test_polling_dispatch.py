"""Polling dispatch tests for ``CustomResource``.

Verifies the lifecycle-with-polling and poll-re-invocation paths. We mock
the ``setup_polling`` / ``teardown_polling`` calls because they would
otherwise require boto3 / moto. The integration tests cover the full
end-to-end flow.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest

from cfn_handler import CustomResource
from cfn_handler._internal.poller import (
    EVENT_MARKER_PERMISSION,
    EVENT_MARKER_POLL,
    EVENT_MARKER_RULE,
)
from cfn_handler.exceptions import CfnHandlerError
from cfn_handler.resource import LambdaContext

# ---- Initial lifecycle invocation with poller registered ----------------


def test_create_with_poll_handler_defers_response(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Lifecycle handler runs, then setup_polling is called and NO response sent."""
    resource = CustomResource()  # NOT test_mode: we want to verify setup_polling

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with (
        patch("cfn_handler.resource.setup_polling") as setup,
        patch("cfn_handler.resource.send_response") as send,
    ):
        resource(events["Create"], mock_context)

    setup.assert_called_once()
    send.assert_not_called()


def test_create_with_poll_handler_in_test_mode_records_sentinel(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Test-mode polling records a sentinel on last_response so tests can assert intent."""
    resource = CustomResource(test_mode=True)

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"foo": "bar"}

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    resource(events["Create"], mock_context)
    assert resource.last_response is not None
    assert resource.last_response.get("__cfn_handler_polling__") is True
    assert resource.last_response.get("Data") == {"foo": "bar"}


def test_setup_polling_failure_yields_failed_response(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """If setup_polling raises (e.g. boto3 missing), we must still answer CFN."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with (
        patch(
            "cfn_handler.resource.setup_polling",
            side_effect=CfnHandlerError("boto3 missing"),
        ),
        patch("cfn_handler.resource.send_response") as send,
    ):
        resource(events["Create"], mock_context)

    send.assert_called_once()
    payload = send.call_args.args[1]
    assert payload["Status"] == "FAILED"
    assert "boto3 missing" in payload["Reason"]


# ---- Poll re-invocation -------------------------------------------------


@pytest.fixture
def poll_event_create(events: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A poll-re-invocation event for the Create lifecycle."""
    e = events["Create"]
    e[EVENT_MARKER_POLL] = True
    e[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/MyRuleName"
    e[EVENT_MARKER_PERMISSION] = "Sid1"
    e["PhysicalResourceId"] = "previously-set-pid"
    return e


def test_poll_continue_returns_without_responding(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """Poll handler returning None means 'still running': no response, no teardown."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    send.assert_not_called()
    teardown.assert_not_called()


def test_poll_completion_sends_success_and_tears_down(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """Poll returning a dict means done: SUCCESS response + cleanup."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"Endpoint": "https://x.example"}

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    send.assert_called_once()
    payload = send.call_args.args[1]
    assert payload["Status"] == "SUCCESS"
    assert payload["Data"] == {"Endpoint": "https://x.example"}
    teardown.assert_called_once()


def test_poll_failure_sends_failed_and_tears_down(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """Poll raising means failed: FAILED response + cleanup."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        raise RuntimeError("operation failed in poll")

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    payload = send.call_args.args[1]
    assert payload["Status"] == "FAILED"
    assert "operation failed in poll" in payload["Reason"]
    teardown.assert_called_once()


def test_poll_with_insufficient_time_fails(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """If the safety margin would be exceeded, fail fast rather than risk hanging."""
    mock_context.get_remaining_time_in_millis = Mock(return_value=5_000)  # 5s, below default 30s margin
    resource = CustomResource()

    poller_called = []

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        poller_called.append(True)
        return None

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    assert poller_called == []  # poll handler MUST NOT be invoked
    payload = send.call_args.args[1]
    assert payload["Status"] == "FAILED"
    assert "timed out" in payload["Reason"].lower() or "insufficient" in payload["Reason"].lower()
    teardown.assert_called_once()


def test_poll_event_with_unknown_request_type_fails(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    poll_event_create["RequestType"] = "Bogus"
    resource = CustomResource()

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    assert send.call_args.args[1]["Status"] == "FAILED"
    teardown.assert_called_once()


def test_poll_event_without_registered_handler_fails(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """Re-invoked but the user removed the poll handler? Best-effort failure."""
    resource = CustomResource()
    # No poll handler registered.

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling") as teardown,
    ):
        resource(poll_event_create, mock_context)

    assert send.call_args.args[1]["Status"] == "FAILED"
    teardown.assert_called_once()


def test_poll_completion_echoes_existing_physical_resource_id(
    poll_event_create: dict[str, Any],
    mock_context: Mock,
) -> None:
    """The PhysicalResourceId from the original event must survive poll completion."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"x": "y"}

    with (
        patch("cfn_handler.resource.send_response") as send,
        patch("cfn_handler.resource.teardown_polling"),
    ):
        resource(poll_event_create, mock_context)

    payload = send.call_args.args[1]
    assert payload["PhysicalResourceId"] == "previously-set-pid"
