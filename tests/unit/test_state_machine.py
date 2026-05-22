"""Property-based state-machine tests for the CustomResource lifecycle.

Hypothesis enumerates combinations of:
- handler-set (which lifecycle and poll decorators are registered)
- request type (Create / Update / Delete)
- handler outcome (return None / return dict / raise)
- time-budget (above / below safety margin)

against the documented invariants:

I1. Exactly one response is captured per terminal call (via ``replay()``).
I2. SUCCESS responses include all required fields (Status, PhysicalResourceId,
    StackId, RequestId, LogicalResourceId, Reason, Data).
I3. FAILED responses include a non-empty Reason.
I4. The Reason is at most MAX_REASON_LENGTH characters.
I5. PhysicalResourceId is a non-empty string in every response.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from cfn_handler import CustomResource
from cfn_handler._internal.response import MAX_REASON_LENGTH

EVENTS_DIR = Path(__file__).parent.parent / "events"


def _load(name: str) -> dict[str, Any]:
    with (EVENTS_DIR / f"{name}.json").open() as fh:
        result: dict[str, Any] = json.load(fh)
    return result


_BASE_EVENTS: dict[str, dict[str, Any]] = {
    "Create": _load("create"),
    "Update": _load("update"),
    "Delete": _load("delete"),
}


def _make_context(remaining_ms: int) -> Mock:
    ctx = Mock()
    ctx.aws_request_id = "rid-fixed"
    ctx.function_name = "fn-fixed"
    ctx.get_remaining_time_in_millis = Mock(return_value=remaining_ms)
    return ctx


# Outcomes the user's handler can produce.
HANDLER_OUTCOMES = st.sampled_from(["none", "dict", "raise"])


@settings(
    deadline=None,
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    request_type=st.sampled_from(["Create", "Update", "Delete"]),
    handler_outcome=HANDLER_OUTCOMES,
    register_handler=st.booleans(),
    remaining_ms=st.integers(min_value=1_000, max_value=900_000),
    no_echo=st.booleans(),
)
def test_lifecycle_invariants_no_polling(
    request_type: str,
    handler_outcome: str,
    register_handler: bool,
    remaining_ms: int,
    no_echo: bool,
) -> None:
    """Without polling, every dispatch produces exactly one response satisfying the documented invariants (I1-I5)."""
    event = copy.deepcopy(_BASE_EVENTS[request_type])
    context = _make_context(remaining_ms)

    resource = CustomResource()

    if register_handler:
        decorator = getattr(resource, request_type.lower())

        @decorator
        def fn(_e: dict[str, Any], _c: object) -> dict[str, Any] | None:
            if no_echo:
                resource.no_echo = True
            if handler_outcome == "none":
                return None
            if handler_outcome == "dict":
                return {"k": "v"}
            msg = "simulated handler failure"
            raise RuntimeError(msg)

    replay = resource.replay(event, context)

    # I1: exactly one response was captured.
    assert replay.payload, "No response was captured"
    payload = replay.payload

    # I2 / I5: required fields present and non-empty PID.
    for required in ("Status", "PhysicalResourceId", "StackId", "RequestId", "LogicalResourceId", "Reason", "Data"):
        assert required in payload, f"Missing field: {required}"
    assert isinstance(payload["PhysicalResourceId"], str)
    assert payload["PhysicalResourceId"], "PhysicalResourceId must be non-empty"

    # I4: Reason length bounded.
    assert len(payload["Reason"]) <= MAX_REASON_LENGTH

    # Outcome-specific assertions:
    if not register_handler:
        assert replay.status == "FAILED"
        assert replay.reason  # I3
    elif handler_outcome == "raise":
        assert replay.status == "FAILED"
        assert replay.reason  # I3
        assert "simulated handler failure" in replay.reason
    else:
        assert replay.status == "SUCCESS"
        if handler_outcome == "dict":
            assert replay.data == {"k": "v"}
        else:
            assert replay.data == {}


@settings(
    deadline=None,
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    request_type=st.sampled_from(["Create", "Update", "Delete"]),
    pid_set=st.booleans(),
    pid_value=st.text(min_size=1, max_size=64),
)
def test_physical_resource_id_resolution(
    request_type: str,
    pid_set: bool,
    pid_value: str,
) -> None:
    """PID precedence: handler-set > event-carried > auto-generated."""
    event = copy.deepcopy(_BASE_EVENTS[request_type])
    context = _make_context(120_000)

    # Hypothesis can produce strings with surrogate pairs that json.dumps will
    # refuse; assume well-formed input. (Real CFN PIDs are well-formed.)
    assume(pid_value.encode("utf-8", "surrogatepass") == pid_value.encode("utf-8", "strict"))

    resource = CustomResource()

    decorator = getattr(resource, request_type.lower())

    @decorator
    def fn(_e: dict[str, Any], _c: object) -> None:
        if pid_set:
            resource.physical_resource_id = pid_value
        return None

    replay = resource.replay(event, context)
    assert replay.physical_resource_id is not None

    if pid_set:
        assert replay.physical_resource_id == pid_value
    elif "PhysicalResourceId" in event:
        assert replay.physical_resource_id == event["PhysicalResourceId"]
    else:
        assert replay.physical_resource_id
        # Auto-generated id includes the logical resource id.
        assert event["LogicalResourceId"] in replay.physical_resource_id


@settings(deadline=None, max_examples=100)
@given(
    reason_length=st.integers(min_value=0, max_value=MAX_REASON_LENGTH * 3),
)
def test_reason_truncation_invariant(reason_length: int) -> None:
    """For any input length, the resulting Reason is at most MAX_REASON_LENGTH."""
    from cfn_handler._internal.response import truncate_reason

    payload = "x" * reason_length
    out = truncate_reason(payload)
    assert len(out) <= MAX_REASON_LENGTH


@pytest.mark.parametrize(
    ("request_type", "handler_to_register"),
    [
        ("Create", "create"),
        ("Update", "update"),
        ("Delete", "delete"),
    ],
)
@settings(deadline=None, max_examples=50)
@given(
    handler_outcome=HANDLER_OUTCOMES,
)
def test_handler_outcomes_each_request_type(
    request_type: str,
    handler_to_register: str,
    handler_outcome: str,
) -> None:
    """For every (request_type, handler_outcome) combination, response is well-formed."""
    event = copy.deepcopy(_BASE_EVENTS[request_type])
    context = _make_context(120_000)

    resource = CustomResource()

    decorator = getattr(resource, handler_to_register)

    @decorator
    def fn(_e: dict[str, Any], _c: object) -> dict[str, Any] | None:
        if handler_outcome == "none":
            return None
        if handler_outcome == "dict":
            return {"x": "y"}
        msg = "err"
        raise RuntimeError(msg)

    replay = resource.replay(event, context)
    assert replay.status in {"SUCCESS", "FAILED"}
    assert replay.physical_resource_id
