"""Shared pytest fixtures.

Conventions:
- ``events`` returns a fresh deepcopy of all three lifecycle events; tests can
  mutate without leaking into siblings.
- ``mock_context`` is a Lambda-context-shaped object with sensible defaults.
- ``aws_region_env`` is autouse so any boto3 client construction in tests
  has a region without needing an AWS profile.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

EVENTS_DIR = Path(__file__).parent / "events"


def _load_event(name: str) -> dict[str, Any]:
    with (EVENTS_DIR / f"{name}.json").open() as fh:
        result: dict[str, Any] = json.load(fh)
    return result


@pytest.fixture
def events() -> dict[str, dict[str, Any]]:
    """Fresh deep copy of the three canonical CFN lifecycle events.

    Tests SHOULD mutate the returned dict freely; each test gets its own copy.
    """
    return {
        "Create": copy.deepcopy(_load_event("create")),
        "Update": copy.deepcopy(_load_event("update")),
        "Delete": copy.deepcopy(_load_event("delete")),
    }


@pytest.fixture
def mock_context() -> Mock:
    """Lambda context double with sensible defaults.

    Tests can adjust ``aws_request_id``, ``function_name``, or override the
    ``get_remaining_time_in_millis`` return value as needed::

        mock_context.get_remaining_time_in_millis = Mock(return_value=5000)
    """
    ctx = Mock()
    ctx.aws_request_id = "test-aws-request-id"
    ctx.function_name = "test-function"
    ctx.get_remaining_time_in_millis = Mock(return_value=300_000)  # 5 minutes
    return ctx


@pytest.fixture(autouse=True)
def aws_region_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure AWS_REGION is set so any boto3 client construction succeeds."""
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    yield
