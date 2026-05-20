"""Long-running custom resource using cfn-handler's polling support.

The CREATE handler kicks off the work and returns. cfn-handler then
provisions a CloudWatch Events rule that re-invokes this Lambda every
minute. On each re-invocation the poll handler checks readiness and
returns the response data when done (or raises to signal failure).
"""

from __future__ import annotations

import time
from typing import Any

from cfn_handler import CustomResource

resource = CustomResource()


@resource.create
def on_create(event: dict[str, Any], _context: object) -> None:
    """Kick off the long-running operation. Return immediately; the poll
    handler will be invoked periodically until the operation completes.
    """
    name = event["ResourceProperties"]["Name"]
    # Imagine: queue_long_running_job(name); store the job id somewhere we
    # can read in poll_create. For the example, we just record an absolute
    # deadline 90 seconds in the future.
    deadline = time.time() + 90.0
    resource.physical_resource_id = f"job-{name}-{deadline:.0f}"


@resource.poll_create
def on_poll_create(_event: dict[str, Any], _context: object) -> dict[str, Any] | None:
    """Check if the long-running operation has finished.

    Return ``None`` to indicate "still running" — the library will leave
    the CW Events rule in place and try again next minute.

    Return a ``dict`` to indicate success.
    Raise an exception to indicate failure.
    """
    pid = resource.physical_resource_id  # set by on_create above
    deadline_s = int(pid.rsplit("-", 1)[1])
    if time.time() < deadline_s:
        return None  # keep polling
    return {"Endpoint": "https://api.example.com/long-running", "Status": "Active"}


@resource.delete
def on_delete(_event: dict[str, Any], _context: object) -> None:
    """Tear down. Synchronous in this example; could also be polled."""


def handler(event: dict[str, Any], context: object) -> None:
    """Lambda entrypoint."""
    resource(event, context)  # type: ignore[arg-type]
