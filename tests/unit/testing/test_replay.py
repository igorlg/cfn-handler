"""Tests for ``cfn_handler.testing.Replay`` and ``CustomResource.replay``.

These tests verify the public testing surface end-to-end:
- ``replay()`` returns a structured ``Replay`` value
- No HTTP I/O and no boto3 import occurs during replay
- The dataclass is immutable
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from typing import Any
from unittest.mock import Mock

import pytest

from cfn_handler import CustomResource
from cfn_handler.testing import Replay


def test_replay_returns_success_for_returning_handler(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"Endpoint": "https://x"}

    replay = resource.replay(events["Create"], mock_context)

    assert isinstance(replay, Replay)
    assert replay.status == "SUCCESS"
    assert replay.data == {"Endpoint": "https://x"}
    assert replay.request_type == "Create"
    assert replay.payload["Status"] == "SUCCESS"
    assert replay.payload["Data"] == {"Endpoint": "https://x"}


def test_replay_returns_failed_for_raising_handler(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    replay = resource.replay(events["Create"], mock_context)

    assert replay.status == "FAILED"
    assert "boom" in replay.reason
    assert replay.payload["Status"] == "FAILED"


def test_replay_does_not_perform_http_io(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``replay()`` must NEVER call urllib's PUT path."""

    def boom(*_args: Any, **_kwargs: Any) -> None:
        msg = "urllib must not be invoked during replay"
        raise AssertionError(msg)

    monkeypatch.setattr("cfn_handler._internal.response.urllib.request.urlopen", boom)

    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"x": "y"}

    # Should NOT raise from boom.
    resource.replay(events["Create"], mock_context)


def test_replay_does_not_import_boto3_for_non_polling_path(tmp_path: Any) -> None:
    """A non-polling replay must not import boto3 (run in subprocess for clean sys.modules)."""
    script = tmp_path / "no_boto3.py"
    script.write_text(
        "import sys\n"
        "from cfn_handler import CustomResource\n"
        "from cfn_handler.testing import make_event, make_context\n"
        "\n"
        "resource = CustomResource()\n"
        "\n"
        "@resource.create\n"
        "def on_create(event, ctx):\n"
        "    return {'ok': True}\n"
        "\n"
        "resource.replay(make_event(), make_context())\n"
        "assert 'boto3' not in sys.modules, 'boto3 was imported during replay'\n"
        "print('OK')\n",
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "OK" in result.stdout


def test_replay_dataclass_is_frozen(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"x": 1}

    replay = resource.replay(events["Create"], mock_context)

    with pytest.raises(dataclasses.FrozenInstanceError):
        replay.status = "FAILED"  # type: ignore[misc]


def test_replay_payload_is_complete_response_shape(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """``replay.payload`` is exactly what would have been PUT to CFN."""
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"Endpoint": "x"}

    replay = resource.replay(events["Create"], mock_context)

    # CFN response schema requires these keys.
    for key in ("Status", "PhysicalResourceId", "StackId", "RequestId", "LogicalResourceId", "Reason", "Data"):
        assert key in replay.payload, f"missing {key} in payload"
    assert replay.payload["Status"] == "SUCCESS"
    assert replay.payload["Data"] == {"Endpoint": "x"}


def test_replay_does_not_persist_state_between_calls(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """Two replays on the same instance produce independent results."""
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"i": 1}

    @resource.update
    def on_update(_event: dict[str, Any], _ctx: Any) -> None:
        msg = "update boom"
        raise RuntimeError(msg)

    success = resource.replay(events["Create"], mock_context)
    failure = resource.replay(events["Update"], mock_context)

    assert success.status == "SUCCESS"
    assert failure.status == "FAILED"
    assert "update boom" in failure.reason


def test_replay_without_context_uses_default(
    events: dict[str, dict[str, Any]],
) -> None:
    """When ``context`` is omitted, replay() supplies a default LambdaContext.

    The default context comes from cfn_handler.testing.make_context()
    and provides values that satisfy the LambdaContext Protocol.
    """
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"ok": True}

    replay = resource.replay(events["Create"])
    assert replay.status == "SUCCESS"
    assert replay.data == {"ok": True}
