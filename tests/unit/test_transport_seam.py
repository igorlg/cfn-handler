"""Tests for the internal Transport seam.

The seam allows the response transport (urllib PUT to CFN) to be
swapped for an in-memory capture during testing. This is the foundation
for ``replay()`` and is verified independently here.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

from cfn_handler import CustomResource


def test_transport_callable_intercepts_response(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
) -> None:
    """A custom transport callable replaces the urllib PUT transport.

    When ``CustomResource(transport=...)`` is constructed with a callable,
    that callable receives ``(url, payload)`` instead of urllib being
    invoked. This is the foundational seam for the testing helpers.
    """
    captured: list[tuple[str, dict[str, Any]]] = []

    def fake_transport(url: str, payload: dict[str, Any]) -> None:
        captured.append((url, payload))

    resource = CustomResource(transport=fake_transport)

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"Endpoint": "https://intercepted.example"}

    resource(events["Create"], mock_context)

    assert len(captured) == 1
    url, payload = captured[0]
    assert url == events["Create"]["ResponseURL"]
    assert payload["Status"] == "SUCCESS"
    assert payload["Data"] == {"Endpoint": "https://intercepted.example"}


def test_transport_default_remains_http(
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
    monkeypatch: Any,
) -> None:
    """Without an explicit transport, the urllib PUT path is used.

    Verifies the seam is purely additive: existing behaviour is preserved
    when no transport is supplied.
    """
    sent: list[tuple[str, dict[str, Any]]] = []

    def fake_send_response(url: str, payload: dict[str, Any]) -> None:
        sent.append((url, payload))

    monkeypatch.setattr(
        "cfn_handler.resource.send_response",
        fake_send_response,
    )

    resource = CustomResource()  # no transport= kwarg

    @resource.create
    def on_create(_event: dict[str, Any], _ctx: Any) -> dict[str, Any]:
        return {"x": "y"}

    resource(events["Create"], mock_context)

    assert len(sent) == 1
