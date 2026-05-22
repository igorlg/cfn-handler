"""Tests for the internal poller-stub seam.

The seam allows polling provisioning/teardown (which import boto3 and
provision EventBridge rules) to be swapped for in-memory stubs during
testing. This is the foundation for ``replay()``-based polling tests
that don't require boto3.
"""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import Mock

from cfn_handler import CustomResource


def test_poller_stubs_replace_boto3_calls(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """When poller stubs are injected, no boto3 import or AWS call occurs.

    The stub provisioner records its call args and mutates the event
    with the polling marker keys (matching real ``setup_polling``
    behaviour). The library never reaches into ``cfn_handler._internal.
    poller`` — the seam handles it.
    """
    provision_calls: list[tuple[dict[str, Any], str, int, str | None]] = []
    teardown_calls: list[tuple[dict[str, Any], str, str | None]] = []

    def stub_provision(
        event: dict[str, Any],
        function_name: str,
        polling_interval_minutes: int = 1,
        region: str | None = None,
    ) -> None:
        provision_calls.append((event, function_name, polling_interval_minutes, region))
        # Mutate event the same way real setup_polling does so a
        # subsequent invocation (poll re-invocation) routes correctly.
        event["CfnHandlerPoll"] = True
        event["CfnHandlerRule"] = "arn:aws:events:us-east-1:111111111111:rule/stub"
        event["CfnHandlerPermission"] = "stub-perm-id"

    def stub_teardown(
        event: dict[str, Any],
        function_name: str,
        region: str | None = None,
    ) -> None:
        teardown_calls.append((event, function_name, region))

    # Capturing transport so we don't hit the network either.
    sent: list[tuple[str, dict[str, Any]]] = []

    def fake_transport(url: str, payload: dict[str, Any]) -> None:
        sent.append((url, payload))

    resource = CustomResource(
        transport=fake_transport,
        provision_poller=stub_provision,
        teardown_poller=stub_teardown,
    )

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> None:
        return None

    @resource.poll_create
    def on_poll(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"Endpoint": "https://done.example"}

    # First invocation: lifecycle handler runs, stub provisioner mutates
    # event. No CFN response sent (deferred).
    pre_modules = set(sys.modules)
    resource(events["Create"], mock_context)
    assert "boto3" not in (set(sys.modules) - pre_modules), (
        "boto3 must not have been imported during the deferred-create path"
    )
    assert len(provision_calls) == 1
    assert len(sent) == 0
    assert events["Create"]["CfnHandlerPoll"] is True

    # Second invocation: poll re-invocation routes to the poll handler.
    resource(events["Create"], mock_context)
    assert len(teardown_calls) == 1
    assert len(sent) == 1
    _url, payload = sent[0]
    assert payload["Status"] == "SUCCESS"
    assert payload["Data"] == {"Endpoint": "https://done.example"}
