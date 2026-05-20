"""Failing custom resource — demonstrates how exceptions become FAILED responses.

When your handler raises any exception, cfn-handler catches it and reports
``Status: FAILED`` to CloudFormation with the exception's message as the
``Reason``. The CloudFormation stack rolls back; CloudWatch Logs preserves
the full stack trace (cfn-handler logs it at ERROR level before responding).

This example deliberately fails to illustrate the behaviour. Useful for
testing your stack's rollback paths.
"""

from __future__ import annotations

from typing import Any

from cfn_handler import CustomResource

resource = CustomResource()


class PolicyMisconfiguredError(Exception):
    """Custom exception type — message becomes the CFN Reason."""


@resource.create
def on_create(event: dict[str, Any], _context: object) -> None:
    """Always fail on create to demonstrate the FAILED response path."""
    name = event["ResourceProperties"].get("Name", "<unknown>")
    raise PolicyMisconfiguredError(f"Cannot provision {name}: required IAM policy is missing.")


@resource.update
def on_update(_event: dict[str, Any], _context: object) -> None:
    """Update is fine — we only fail on create."""


@resource.delete
def on_delete(_event: dict[str, Any], _context: object) -> None:
    """Delete should always succeed (otherwise the stack hangs)."""


def handler(event: dict[str, Any], context: object) -> None:
    """Lambda entrypoint."""
    resource(event, context)  # type: ignore[arg-type]
