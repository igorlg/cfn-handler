"""Tests for ``replay()`` polling deferral and re-invocation.

Verifies the two-step polling flow:
1. First replay: lifecycle handler runs, polling is "provisioned" (stubbed),
   no response is emitted, ``Replay(status="DEFERRED")`` returned.
2. Second replay (with the mutated event): the poll handler runs, response
   is emitted, ``Replay(status="SUCCESS"/"FAILED")`` returned.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from cfn_handler import CustomResource
from cfn_handler._internal.poller import (
    EVENT_MARKER_PERMISSION,
    EVENT_MARKER_POLL,
    EVENT_MARKER_RULE,
)


def test_replay_with_poll_handler_returns_deferred(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """First replay defers, no response emitted, event mutated with markers."""
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"InitialData": "x"}

    @resource.poll_create
    def on_poll(_event: dict[str, Any], _ctx: Any) -> None:
        return None  # would continue polling

    event = events["Create"]
    replay = resource.replay(event, mock_context)

    assert replay.status == "DEFERRED"
    assert replay.payload == {}
    assert replay.physical_resource_id is None
    # Event has been mutated so a follow-up replay routes to the poll handler.
    assert event[EVENT_MARKER_POLL] is True
    assert event[EVENT_MARKER_RULE].startswith("arn:aws:events:")
    assert isinstance(event[EVENT_MARKER_PERMISSION], str)


def test_replay_resumes_into_poll_handler_with_mutated_event(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Second replay (with markers from the first) routes to the poll handler."""
    resource = CustomResource()

    poll_calls: list[bool] = []

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> None:
        return None

    @resource.poll_create
    def on_poll(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        poll_calls.append(True)
        return {"Endpoint": "https://done.example"}

    event = events["Create"]

    # Step 1: defer.
    deferred = resource.replay(event, mock_context)
    assert deferred.status == "DEFERRED"
    assert poll_calls == []  # poll handler NOT called yet

    # Step 2: resume — same event, now with marker keys.
    final = resource.replay(event, mock_context)
    assert final.status == "SUCCESS"
    assert final.data == {"Endpoint": "https://done.example"}
    assert poll_calls == [True]


def test_replay_resumes_with_poll_handler_failure(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Poll handler raising on the resume step produces FAILED."""
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> None:
        return None

    @resource.poll_create
    def on_poll(_event: dict[str, Any], _ctx: Any) -> None:
        msg = "polling step failed"
        raise RuntimeError(msg)

    event = events["Create"]
    resource.replay(event, mock_context)
    final = resource.replay(event, mock_context)

    assert final.status == "FAILED"
    assert "polling step failed" in final.reason


def test_replay_does_not_mutate_event_when_no_poll_handler(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """A non-polled handler doesn't touch the event."""
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"x": 1}

    event = events["Create"]
    replay = resource.replay(event, mock_context)

    assert replay.status == "SUCCESS"
    assert EVENT_MARKER_POLL not in event
    assert EVENT_MARKER_RULE not in event
    assert EVENT_MARKER_PERMISSION not in event
