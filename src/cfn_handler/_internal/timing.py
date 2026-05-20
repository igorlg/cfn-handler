"""Lambda timing helpers.

Pure functions that read the Lambda execution context's remaining-time budget
and decide whether the polling loop has time to run another iteration.
"""

from __future__ import annotations

from typing import Any

#: Default safety margin (in milliseconds) reserved for response sending and
#: cleanup. If less than this remains, the resource is failed with a timeout
#: reason rather than risking an unresponsive Lambda.
DEFAULT_SAFETY_MARGIN_MS = 30_000


def remaining_time_ms(context: Any) -> int | None:
    """Return remaining execution time in milliseconds.

    Returns ``None`` when ``context`` does not expose
    ``get_remaining_time_in_millis()`` (e.g. SAM-local invocations or test
    doubles passing a plain dict).

    Args:
        context: The Lambda invocation context.

    Returns:
        Remaining time in milliseconds, or ``None`` if the context cannot
        report it.
    """
    getter = getattr(context, "get_remaining_time_in_millis", None)
    if getter is None:
        return None
    try:
        return int(getter())
    except (TypeError, ValueError):
        return None


def has_time_for_iteration(
    context: Any,
    safety_margin_ms: int = DEFAULT_SAFETY_MARGIN_MS,
) -> bool:
    """Decide whether enough time remains for another poll iteration.

    Returns ``True`` if ``context`` cannot report remaining time (we assume
    the runtime knows what it is doing) or if remaining time exceeds the
    safety margin.
    """
    remaining = remaining_time_ms(context)
    if remaining is None:
        return True
    return remaining > safety_margin_ms
