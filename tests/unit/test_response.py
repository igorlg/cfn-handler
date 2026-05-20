"""Unit tests for ``_internal/response.py``.

Covers payload construction, reason truncation, and the HTTP transport
including success, HTTPError, URLError, and JSON-encoding-failure paths.
"""

from __future__ import annotations

import json
import urllib.error
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from cfn_handler._internal.response import (
    MAX_REASON_LENGTH,
    build_response,
    send_response,
    truncate_reason,
)
from cfn_handler.exceptions import ResponseError

# ---- truncate_reason -----------------------------------------------------


def test_truncate_reason_under_limit_returns_unchanged() -> None:
    short = "short reason"
    assert truncate_reason(short) == short


def test_truncate_reason_at_limit_returns_unchanged() -> None:
    text = "x" * MAX_REASON_LENGTH
    assert truncate_reason(text) == text


def test_truncate_reason_over_limit_truncates_with_ellipsis() -> None:
    text = "a" * (MAX_REASON_LENGTH + 100)
    result = truncate_reason(text)
    assert len(result) == MAX_REASON_LENGTH
    assert result.endswith("...")


def test_truncate_reason_preserves_tail_of_message() -> None:
    """Truncation keeps the *end* of the string (where the actual error is)."""
    head = "x" * MAX_REASON_LENGTH
    tail = "ACTUAL_ERROR_MARKER"
    result = truncate_reason(head + tail)
    assert tail in result


def test_truncate_reason_with_custom_limit() -> None:
    # 11-char input, limit 8: keep last (8 - 3) = 5 chars + "..." => "world..."
    assert truncate_reason("hello world", limit=8) == "world..."


# ---- build_response -----------------------------------------------------


def test_build_response_success_minimal() -> None:
    payload = build_response(
        status="SUCCESS",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
    )
    assert payload == {
        "Status": "SUCCESS",
        "PhysicalResourceId": "phys-id-1",
        "StackId": "stk",
        "RequestId": "req",
        "LogicalResourceId": "lrid",
        "Reason": "",
        "Data": {},
    }


def test_build_response_failed_with_reason() -> None:
    payload = build_response(
        status="FAILED",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
        reason="something broke",
    )
    assert payload["Status"] == "FAILED"
    assert payload["Reason"] == "something broke"


def test_build_response_with_data() -> None:
    payload = build_response(
        status="SUCCESS",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
        data={"Endpoint": "https://x.example"},
    )
    assert payload["Data"] == {"Endpoint": "https://x.example"}


def test_build_response_no_echo_omitted_when_false() -> None:
    payload = build_response(
        status="SUCCESS",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
        no_echo=False,
    )
    assert "NoEcho" not in payload


def test_build_response_no_echo_set_when_true() -> None:
    payload = build_response(
        status="SUCCESS",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
        no_echo=True,
    )
    assert payload["NoEcho"] is True


def test_build_response_truncates_long_reason() -> None:
    payload = build_response(
        status="FAILED",
        physical_resource_id="phys-id-1",
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
        reason="x" * (MAX_REASON_LENGTH + 100),
    )
    assert len(payload["Reason"]) == MAX_REASON_LENGTH
    assert payload["Reason"].endswith("...")


def test_build_response_coerces_physical_resource_id_to_str() -> None:
    payload = build_response(
        status="SUCCESS",
        physical_resource_id=12345,  # type: ignore[arg-type]
        stack_id="stk",
        request_id="req",
        logical_resource_id="lrid",
    )
    assert payload["PhysicalResourceId"] == "12345"


# ---- send_response ------------------------------------------------------


def _make_urlopen_response(status: int = 200, reason: str = "OK") -> MagicMock:
    """Build a context-manager-shaped urlopen response."""
    response = MagicMock()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=None)
    response.status = status
    response.reason = reason
    return response


def test_send_response_happy_path() -> None:
    payload: dict[str, Any] = {"Status": "SUCCESS"}
    fake_response = _make_urlopen_response(200, "OK")

    with patch("cfn_handler._internal.response.urllib.request.urlopen", return_value=fake_response) as urlopen:
        send_response("https://example.com/cfn", payload)

    assert urlopen.call_count == 1
    request = urlopen.call_args.args[0]
    assert request.get_method() == "PUT"
    assert request.full_url == "https://example.com/cfn"
    assert json.loads(request.data.decode("utf-8")) == payload


def test_send_response_non_2xx_raises_response_error() -> None:
    fake_response = _make_urlopen_response(500, "Internal Server Error")

    with (
        patch("cfn_handler._internal.response.urllib.request.urlopen", return_value=fake_response),
        pytest.raises(ResponseError, match="HTTP 500"),
    ):
        send_response("https://example.com/cfn", {"Status": "SUCCESS"})


def test_send_response_http_error_raises_response_error() -> None:
    err = urllib.error.HTTPError(
        url="https://example.com/cfn",
        code=403,
        msg="Forbidden",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )
    try:
        with (
            patch("cfn_handler._internal.response.urllib.request.urlopen", side_effect=err),
            pytest.raises(ResponseError, match="HTTP 403") as exc_info,
        ):
            send_response("https://example.com/cfn", {"Status": "SUCCESS"})
        assert exc_info.value.__cause__ is err
    finally:
        err.close()


def test_send_response_url_error_raises_response_error() -> None:
    err = urllib.error.URLError("connection refused")
    with (
        patch("cfn_handler._internal.response.urllib.request.urlopen", side_effect=err),
        pytest.raises(ResponseError, match="Failed to reach") as exc_info,
    ):
        send_response("https://example.com/cfn", {"Status": "SUCCESS"})
    assert exc_info.value.__cause__ is err


def test_send_response_json_serialization_failure_raises_response_error() -> None:
    class Unserializable:
        pass

    payload = {"Status": "SUCCESS", "Data": {"x": Unserializable()}}
    with pytest.raises(ResponseError, match="JSON-encode") as exc_info:
        send_response("https://example.com/cfn", payload)
    assert isinstance(exc_info.value.__cause__, TypeError)
