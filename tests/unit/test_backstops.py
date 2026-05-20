"""Targeted tests for error-path / backstop branches in CustomResource.

These exercise the safety nets we never want to hit in production but must
exist (and be tested) so that CloudFormation never hangs on us.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

from cfn_handler import CustomResource
from cfn_handler._internal.poller import EVENT_MARKER_PERMISSION, EVENT_MARKER_POLL, EVENT_MARKER_RULE
from cfn_handler.exceptions import ResponseError
from cfn_handler.resource import LambdaContext


def test_catastrophic_dispatch_error_triggers_best_effort_failed(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """If _dispatch itself raises, the backstop sends a FAILED to CFN."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    # Force _dispatch_lifecycle to raise an unexpected error.
    with (
        patch.object(resource, "_dispatch_lifecycle", side_effect=KeyError("entirely unexpected")),
        patch("cfn_handler.resource.send_response") as send,
    ):
        resource(events["Create"], mock_context)

    # The backstop must produce a FAILED response.
    assert send.call_count == 1
    payload = send.call_args.args[1]
    assert payload["Status"] == "FAILED"
    assert "Internal error" in payload["Reason"]


def test_response_error_at_top_level_is_swallowed(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """ResponseError must not propagate out of __call__.

    If it did, AWS Lambda would mark the invocation as failed and the
    CloudFormation custom-resource flow would lose the response signal.
    """
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    err = ResponseError("simulated network error")
    # Force _dispatch to raise ResponseError directly so the top-level catch
    # in __call__ handles it (rather than being absorbed by _emit_response).
    with patch.object(resource, "_dispatch", side_effect=err):
        # Should not raise:
        resource(events["Create"], mock_context)


def test_emit_response_swallows_response_error(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """_emit_response must catch ResponseError so __call__ continues cleanly."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    with patch(
        "cfn_handler.resource.send_response",
        side_effect=ResponseError("simulated"),
    ):
        # Must not raise:
        resource(events["Create"], mock_context)


def test_best_effort_failed_swallows_double_failure(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """If even the FAILED response can't be sent, we still must not raise."""
    resource = CustomResource()

    @resource.create
    def on_create(_e: dict[str, Any], _c: LambdaContext) -> None:
        return None

    # Make _dispatch raise (catastrophic), AND make _send_failed raise too.
    with (
        patch.object(resource, "_dispatch_lifecycle", side_effect=KeyError("oops")),
        patch.object(resource, "_send_failed", side_effect=RuntimeError("everything is on fire")),
    ):
        # Should not raise; logger.exception records both failures.
        resource(events["Create"], mock_context)


def test_safe_teardown_swallows_teardown_error(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """If teardown_polling raises, we still must complete dispatch cleanly."""
    poll_event = events["Create"]
    poll_event[EVENT_MARKER_POLL] = True
    poll_event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/my-rule"
    poll_event[EVENT_MARKER_PERMISSION] = "Sid"

    resource = CustomResource()

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"done": True}

    with (
        patch("cfn_handler.resource.send_response"),
        patch(
            "cfn_handler.resource.teardown_polling",
            side_effect=RuntimeError("teardown failed"),
        ),
    ):
        # Should not raise:
        resource(poll_event, mock_context)


def test_safe_teardown_skipped_in_test_mode(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """In test_mode, no teardown is attempted (we never set up either)."""
    poll_event = events["Create"]
    poll_event[EVENT_MARKER_POLL] = True
    poll_event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/my-rule"
    poll_event[EVENT_MARKER_PERMISSION] = "Sid"

    resource = CustomResource(test_mode=True)

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"done": True}

    with patch("cfn_handler.resource.teardown_polling") as teardown:
        resource(poll_event, mock_context)

    teardown.assert_not_called()
