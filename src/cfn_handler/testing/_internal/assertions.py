"""Assertion helpers for replay-based unit tests.

Each helper raises ``AssertionError`` with an informative message on
failure, and returns ``None`` on success. Optional kwargs are matched
only when explicitly supplied (so ``assert_success(replay)`` just checks
the status, while ``assert_success(replay, data={...})`` adds a data
match).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cfn_handler.testing._internal.replay_result import Replay


def assert_success(
    replay: Replay,
    *,
    data: dict[str, Any] | None = None,
    physical_resource_id: str | None = None,
    no_echo: bool | None = None,
) -> None:
    """Assert ``replay`` represents a SUCCESS, optionally matching fields.

    Args:
        replay: The :class:`Replay` to inspect.
        data: When supplied, requires ``replay.data == data`` (exact
            match). Pass ``None`` to ignore.
        physical_resource_id: When supplied, requires
            ``replay.physical_resource_id == physical_resource_id``.
        no_echo: When supplied, requires ``replay.no_echo == no_echo``.

    Raises:
        AssertionError: When any condition fails. The message includes
            both the expected and actual values.
    """
    if replay.status != "SUCCESS":
        msg = f"expected status='SUCCESS', got status={replay.status!r}; reason={replay.reason!r}; data={replay.data!r}"
        raise AssertionError(msg)

    if data is not None and replay.data != data:
        msg = f"expected data={data!r}, got data={replay.data!r}"
        raise AssertionError(msg)

    if physical_resource_id is not None and replay.physical_resource_id != physical_resource_id:
        msg = (
            f"expected physical_resource_id={physical_resource_id!r}, "
            f"got physical_resource_id={replay.physical_resource_id!r}"
        )
        raise AssertionError(msg)

    if no_echo is not None and replay.no_echo != no_echo:
        msg = f"expected no_echo={no_echo!r}, got no_echo={replay.no_echo!r}"
        raise AssertionError(msg)


def assert_failed(
    replay: Replay,
    *,
    reason_contains: str | None = None,
    physical_resource_id: str | None = None,
) -> None:
    """Assert ``replay`` represents a FAILED, optionally matching reason.

    Args:
        replay: The :class:`Replay` to inspect.
        reason_contains: When supplied, requires the substring to appear
            anywhere in ``replay.reason``. Pass ``None`` to ignore.
        physical_resource_id: When supplied, requires
            ``replay.physical_resource_id == physical_resource_id``.

    Raises:
        AssertionError: When any condition fails.
    """
    if replay.status != "FAILED":
        msg = f"expected status='FAILED', got status={replay.status!r}; reason={replay.reason!r}"
        raise AssertionError(msg)

    if reason_contains is not None and reason_contains not in replay.reason:
        msg = f"expected reason to contain {reason_contains!r}, got reason={replay.reason!r}"
        raise AssertionError(msg)

    if physical_resource_id is not None and replay.physical_resource_id != physical_resource_id:
        msg = (
            f"expected physical_resource_id={physical_resource_id!r}, "
            f"got physical_resource_id={replay.physical_resource_id!r}"
        )
        raise AssertionError(msg)


def assert_deferred(replay: Replay) -> None:
    """Assert ``replay`` represents a DEFERRED outcome (entered polling).

    Args:
        replay: The :class:`Replay` to inspect.

    Raises:
        AssertionError: If ``replay.status != "DEFERRED"``.
    """
    if replay.status != "DEFERRED":
        msg = (
            f"expected status='DEFERRED' (would have entered polling), "
            f"got status={replay.status!r}; payload={replay.payload!r}"
        )
        raise AssertionError(msg)
