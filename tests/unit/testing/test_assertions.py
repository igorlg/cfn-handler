"""Tests for ``assert_success``, ``assert_failed``, ``assert_deferred``."""

from __future__ import annotations

import pytest

from cfn_handler.testing import (
    Replay,
    assert_deferred,
    assert_failed,
    assert_success,
)


def _success(
    *,
    data: dict[str, object] | None = None,
    physical_resource_id: str = "test-pid",
    no_echo: bool = False,
) -> Replay:
    payload_data = data if data is not None else {}
    return Replay(
        status="SUCCESS",
        physical_resource_id=physical_resource_id,
        data=payload_data,
        reason="",
        no_echo=no_echo,
        payload={
            "Status": "SUCCESS",
            "PhysicalResourceId": physical_resource_id,
            "Data": payload_data,
            "Reason": "",
        },
        request_type="Create",
    )


def _failed(*, reason: str = "boom", physical_resource_id: str = "test-pid") -> Replay:
    return Replay(
        status="FAILED",
        physical_resource_id=physical_resource_id,
        data={},
        reason=reason,
        no_echo=False,
        payload={
            "Status": "FAILED",
            "PhysicalResourceId": physical_resource_id,
            "Data": {},
            "Reason": reason,
        },
        request_type="Create",
    )


def _deferred() -> Replay:
    return Replay(
        status="DEFERRED",
        physical_resource_id=None,
        data={},
        reason="",
        no_echo=False,
        payload={},
        request_type="Create",
    )


# ---- assert_success ---------------------------------------------------


def test_assert_success_passes_on_success_replay() -> None:
    assert_success(_success())  # should not raise


def test_assert_success_with_data_match_passes() -> None:
    assert_success(_success(data={"x": 1}), data={"x": 1})


def test_assert_success_with_data_mismatch_raises() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_success(_success(data={"x": 1}), data={"x": 2})
    assert "data" in str(excinfo.value).lower()


def test_assert_success_with_physical_resource_id_match_passes() -> None:
    assert_success(_success(physical_resource_id="abc"), physical_resource_id="abc")


def test_assert_success_with_physical_resource_id_mismatch_raises() -> None:
    with pytest.raises(AssertionError):
        assert_success(_success(physical_resource_id="abc"), physical_resource_id="xyz")


def test_assert_success_with_no_echo_match_passes() -> None:
    assert_success(_success(no_echo=True), no_echo=True)


def test_assert_success_with_no_echo_mismatch_raises() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_success(_success(no_echo=False), no_echo=True)
    assert "no_echo" in str(excinfo.value)


def test_assert_success_on_failed_replay_raises_with_reason_in_message() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_success(_failed(reason="something broke"))
    msg = str(excinfo.value)
    assert "FAILED" in msg
    assert "something broke" in msg


def test_assert_success_on_deferred_replay_raises() -> None:
    with pytest.raises(AssertionError):
        assert_success(_deferred())


# ---- assert_failed ----------------------------------------------------


def test_assert_failed_passes_on_failed_replay() -> None:
    assert_failed(_failed())  # should not raise


def test_assert_failed_with_reason_substring_passes() -> None:
    assert_failed(_failed(reason="something boom happened"), reason_contains="boom")


def test_assert_failed_with_reason_substring_mismatch_raises() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_failed(_failed(reason="something boom happened"), reason_contains="kaboom")
    assert "kaboom" in str(excinfo.value)


def test_assert_failed_on_success_replay_raises() -> None:
    with pytest.raises(AssertionError):
        assert_failed(_success())


def test_assert_failed_on_deferred_replay_raises() -> None:
    with pytest.raises(AssertionError):
        assert_failed(_deferred())


def test_assert_failed_with_physical_resource_id_match() -> None:
    assert_failed(_failed(physical_resource_id="abc"), physical_resource_id="abc")


def test_assert_failed_with_physical_resource_id_mismatch_raises() -> None:
    with pytest.raises(AssertionError) as excinfo:
        assert_failed(_failed(physical_resource_id="abc"), physical_resource_id="xyz")
    assert "physical_resource_id" in str(excinfo.value)


# ---- assert_deferred --------------------------------------------------


def test_assert_deferred_passes_on_deferred_replay() -> None:
    assert_deferred(_deferred())


def test_assert_deferred_on_success_raises() -> None:
    with pytest.raises(AssertionError):
        assert_deferred(_success())


def test_assert_deferred_on_failed_raises() -> None:
    with pytest.raises(AssertionError):
        assert_deferred(_failed())
