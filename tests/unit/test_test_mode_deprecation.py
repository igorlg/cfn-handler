"""Tests for the soft-deprecation of ``CustomResource(test_mode=True)``.

In v1.3 the legacy ``test_mode`` flag continues to work, but constructing
a ``CustomResource`` with ``test_mode=True`` emits a ``DeprecationWarning``
directing users at the new ``replay()`` API. Removed in v2.0.
"""

from __future__ import annotations

import warnings
from typing import Any
from unittest.mock import Mock, patch

from cfn_handler import CustomResource
from cfn_handler._internal.poller import EVENT_MARKER_PERMISSION, EVENT_MARKER_POLL, EVENT_MARKER_RULE
from cfn_handler.resource import LambdaContext


def test_test_mode_emits_deprecation_warning() -> None:
    """Construction with ``test_mode=True`` emits ``DeprecationWarning``."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        CustomResource(test_mode=True)
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(deprecations) == 1, f"expected 1 DeprecationWarning, got {len(deprecations)}: {caught}"
    msg = str(deprecations[0].message)
    assert "replay" in msg.lower(), f"deprecation message should mention replay(): {msg!r}"
    assert "cfn_handler.testing" in msg, f"message should reference the new module: {msg!r}"


def test_test_mode_false_does_not_warn() -> None:
    """Constructing without ``test_mode=True`` is silent."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        CustomResource()  # default test_mode=False
        CustomResource(test_mode=False)  # explicit False
    deprecations = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert deprecations == []


def test_test_mode_still_works_for_backwards_compat() -> None:
    """The legacy behaviour continues to function despite the deprecation."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resource = CustomResource(test_mode=True)
    assert resource._test_mode is True
    assert resource.last_response is None


def test_test_mode_safe_teardown_skipped(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """In legacy ``test_mode``, no teardown is attempted (we never set up either).

    This behaviour is preserved verbatim in v1.3 for backwards compatibility.
    Removed in v2.0 along with ``test_mode`` itself.
    """
    poll_event = events["Create"]
    poll_event[EVENT_MARKER_POLL] = True
    poll_event[EVENT_MARKER_RULE] = "arn:aws:events:us-east-1:123:rule/my-rule"
    poll_event[EVENT_MARKER_PERMISSION] = "Sid"

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        resource = CustomResource(test_mode=True)

    @resource.poll_create
    def on_poll(_e: dict[str, Any], _c: LambdaContext) -> dict[str, Any]:
        return {"done": True}

    with patch("cfn_handler.resource.teardown_polling") as teardown:
        resource(poll_event, mock_context)

    teardown.assert_not_called()


def test_test_mode_polling_records_sentinel(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """In legacy ``test_mode``, polling deferral writes a ``__cfn_handler_polling__`` sentinel to ``last_response``.

    Preserved in v1.3 for backwards compatibility. Replaced in v2.0 by
    ``replay()`` which returns ``Replay(status="DEFERRED")``.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
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
