"""Basic CloudFormation Custom Resource using cfn-handler.

This handler demonstrates the simplest case: a synchronous Create / Update /
Delete cycle with no polling, returning data that the parent CFN template
can reference via Fn::GetAtt.
"""

from __future__ import annotations

from typing import Any

from cfn_handler import CustomResource

resource = CustomResource()


@resource.create
def on_create(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Provision the resource and return its public attributes."""
    name = event["ResourceProperties"]["Name"]
    # Imagine: api_call_to_create(name)
    return {
        "Endpoint": f"https://api.example.com/{name}",
        "Status": "Active",
    }


@resource.update
def on_update(event: dict[str, Any], _context: object) -> dict[str, Any]:
    """Re-publish attributes; non-replaceable update."""
    name = event["ResourceProperties"]["Name"]
    return {
        "Endpoint": f"https://api.example.com/{name}",
        "Status": "Active",
    }


@resource.delete
def on_delete(_event: dict[str, Any], _context: object) -> None:
    """Tear down the resource. Empty data on success."""
    # Imagine: api_call_to_delete(...)


def handler(event: dict[str, Any], context: object) -> None:
    """Lambda entrypoint."""
    resource(event, context)  # type: ignore[arg-type]
