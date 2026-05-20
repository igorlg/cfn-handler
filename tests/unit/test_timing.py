"""Unit tests for ``_internal/timing.py``."""

from __future__ import annotations

from unittest.mock import Mock

from cfn_handler._internal.timing import (
    DEFAULT_SAFETY_MARGIN_MS,
    has_time_for_iteration,
    remaining_time_ms,
)


def test_remaining_time_ms_with_real_context() -> None:
    ctx = Mock()
    ctx.get_remaining_time_in_millis = Mock(return_value=12345)
    assert remaining_time_ms(ctx) == 12345


def test_remaining_time_ms_returns_none_when_attribute_missing() -> None:
    """Plain dict has no ``get_remaining_time_in_millis``."""
    assert remaining_time_ms({}) is None


def test_remaining_time_ms_returns_none_when_getter_raises() -> None:
    """Bad mock setups (e.g. SAM-local doubles) get None instead of crashing."""
    ctx = Mock()
    ctx.get_remaining_time_in_millis = Mock(side_effect=TypeError("bad"))
    assert remaining_time_ms(ctx) is None


def test_has_time_for_iteration_true_when_above_margin() -> None:
    ctx = Mock()
    ctx.get_remaining_time_in_millis = Mock(return_value=DEFAULT_SAFETY_MARGIN_MS + 60_000)
    assert has_time_for_iteration(ctx) is True


def test_has_time_for_iteration_false_when_below_margin() -> None:
    ctx = Mock()
    ctx.get_remaining_time_in_millis = Mock(return_value=DEFAULT_SAFETY_MARGIN_MS - 1)
    assert has_time_for_iteration(ctx) is False


def test_has_time_for_iteration_assumes_yes_when_no_getter() -> None:
    """If we cannot ask, assume the runtime knows what it is doing."""
    assert has_time_for_iteration({}) is True


def test_has_time_for_iteration_with_custom_margin() -> None:
    ctx = Mock()
    ctx.get_remaining_time_in_millis = Mock(return_value=10_000)
    assert has_time_for_iteration(ctx, safety_margin_ms=5_000) is True
    assert has_time_for_iteration(ctx, safety_margin_ms=15_000) is False
