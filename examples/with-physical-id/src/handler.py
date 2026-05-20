"""Custom resource that demonstrates explicit ``physical_resource_id`` control.

Most resources should let cfn-handler auto-generate the physical id. This
example shows two cases where you'd override it:

1. **Stable, meaningful id** — set it on CREATE so users browsing CFN
   stack events see something readable instead of a random string.
2. **Replacement on UPDATE** — return a NEW id from UPDATE to signal that
   CloudFormation should treat the change as a replacement (CFN will
   then issue a DELETE for the old id after the UPDATE response).
"""

from __future__ import annotations

from typing import Any

from cfn_handler import CustomResource

resource = CustomResource()


@resource.create
def on_create(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Set a meaningful physical resource id."""
    name = event["ResourceProperties"]["Name"]
    resource.physical_resource_id = f"thing/{name}/v1"
    return {"Url": f"https://example.com/{name}"}


@resource.update
def on_update(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Replace on Name change.

    Returning a new physical_resource_id signals CFN to replace the resource;
    CFN will subsequently call our DELETE with the OLD id once UPDATE
    succeeds.
    """
    old_props = event.get("OldResourceProperties", {})
    new_props = event["ResourceProperties"]

    if old_props.get("Name") != new_props.get("Name"):
        # New id == replacement
        resource.physical_resource_id = f"thing/{new_props['Name']}/v1"
    # else: leave physical_resource_id unset; library echoes the existing one

    return {"Url": f"https://example.com/{new_props['Name']}"}


@resource.delete
def on_delete(event: dict[str, Any], _context: object) -> None:
    """Tear down using the physical resource id from the event."""
    pid = event["PhysicalResourceId"]
    # Imagine: api_call_to_delete(pid)
    _ = pid


def handler(event: dict[str, Any], context: object) -> None:
    """Lambda entrypoint."""
    resource(event, context)  # type: ignore[arg-type]
