"""Parity test: ``CustomResource.__call__`` (real path) vs ``replay()`` (in-process).

For the same handler logic and event, both paths must produce equivalent
response payloads. This test catches drift between the production dispatch
and the replay-based testing surface.

The PhysicalResourceId carries a per-invocation random suffix so we mask
that (and the RequestId echo) before comparison.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
from moto import mock_aws

from cfn_handler import CustomResource
from cfn_handler.resource import LambdaContext


@pytest.fixture
def moto_aws() -> Iterator[None]:
    with mock_aws():
        yield


@pytest.fixture
def captured_payloads(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture every PUT to the simulated CFN ResponseURL.

    Returns the list of payloads (in order) the production path would have
    PUT to CloudFormation. We can then compare to ``replay()`` output.
    """
    captured: list[dict[str, Any]] = []

    class _FakeResponse:
        status = 200
        reason = "OK"

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(request: urllib.request.Request) -> _FakeResponse:
        body = request.data
        if isinstance(body, bytes):
            captured.append(json.loads(body.decode("utf-8")))
        return _FakeResponse()

    monkeypatch.setattr(
        "cfn_handler._internal.response.urllib.request.urlopen",
        fake_urlopen,
    )
    return captured


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip per-invocation random/echo fields for cross-run comparison."""
    keys = ("Status", "Data", "Reason", "LogicalResourceId", "StackId")
    return {k: payload[k] for k in keys if k in payload}


@pytest.mark.integration
def test_production_call_and_replay_produce_equivalent_payloads(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
    moto_aws: None,
    captured_payloads: list[dict[str, Any]],
) -> None:
    """Same handler, two paths, equivalent payloads."""

    def build_resource() -> CustomResource:
        resource = CustomResource()

        @resource.create
        def on_create(_event: dict[str, Any], _ctx: LambdaContext) -> dict[str, Any]:
            return {"Endpoint": "https://parity.example", "Token": "abc"}

        return resource

    # ---- Production path: __call__ via fake_urlopen + moto -------------
    prod_resource = build_resource()
    prod_resource(events["Create"], mock_context)
    assert len(captured_payloads) == 1, "production path did not emit a response"
    prod_payload = captured_payloads[0]

    # ---- Replay path: in-process, no HTTP, no boto3 --------------------
    replay_resource = build_resource()
    replay = replay_resource.replay(events["Create"], mock_context)

    # Status, Data, LogicalResourceId, StackId, Reason MUST agree.
    assert _normalize(prod_payload) == _normalize(replay.payload)
    assert prod_payload["Status"] == replay.status
    assert prod_payload["Data"] == replay.data
