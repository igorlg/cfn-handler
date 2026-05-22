"""The :class:`Replay` dataclass — structured outcome of an in-process dispatch.

Returned by :meth:`cfn_handler.CustomResource.replay`; never mutated by the
library after construction (the dataclass is frozen). Tests inspect the
fields directly or use the assertion helpers in :mod:`cfn_handler.testing`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


def _empty_payload() -> dict[str, Any]:
    """Build an empty payload dict (typed for pyright/mypy strict)."""
    return {}


#: Possible outcomes of a replay. ``"SUCCESS"`` and ``"FAILED"`` mirror real
#: CloudFormation response statuses; ``"DEFERRED"`` is a sentinel value
#: that exists only in replay (never sent on the wire) used to signal
#: "this would have entered polling".
ReplayStatus = Literal["SUCCESS", "FAILED", "DEFERRED"]

#: The lifecycle request type a replay was dispatched on.
ReplayRequestType = Literal["Create", "Update", "Delete"]


@dataclass(frozen=True, slots=True)
class Replay:
    """Outcome of a :meth:`CustomResource.replay` call.

    Attributes:
        status: ``"SUCCESS"``, ``"FAILED"``, or the replay-only sentinel
            ``"DEFERRED"`` (set when the dispatch would have entered
            polling instead of sending a terminal response).
        physical_resource_id: The PhysicalResourceId that would be sent
            to CloudFormation. ``None`` only on a ``DEFERRED`` replay
            where the value isn't computed because no response is built.
        data: The ``Data`` field of the response payload (the dict the
            handler returned, or ``{}`` for handlers returning ``None``
            and for FAILED responses).
        reason: The ``Reason`` field of the response. Empty string on
            SUCCESS; the exception text on FAILED; empty on DEFERRED.
        no_echo: Whether the response would have been marked NoEcho.
        payload: The full rendered response payload that would have been
            PUT to ``ResponseURL``. Empty dict on DEFERRED.
        request_type: ``"Create"``, ``"Update"``, or ``"Delete"`` —
            the value of ``event["RequestType"]`` at replay time.
    """

    status: ReplayStatus
    physical_resource_id: str | None
    data: dict[str, Any]
    reason: str
    no_echo: bool
    payload: dict[str, Any] = field(default_factory=_empty_payload)
    request_type: ReplayRequestType = "Create"
