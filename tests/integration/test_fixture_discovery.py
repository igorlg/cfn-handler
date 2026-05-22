"""End-to-end test that fixtures auto-load via the pytest11 entry point.

We invoke pytest as a subprocess against a fresh project that has NO
conftest.py declaring `pytest_plugins`. If our entry point is wired
correctly, pytest's plugin manager picks up cfn_handler.testing.fixtures
and the four fixtures resolve.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.integration
def test_fixtures_auto_discovered_in_fresh_pytest_project(tmp_path: Path) -> None:
    """A pristine pytest project with no conftest sees our fixtures."""
    test_file = tmp_path / "test_consumer.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            from cfn_handler import CustomResource
            from cfn_handler.testing import assert_success


            def test_uses_fixtures(cfn_create_event, cfn_lambda_context):
                resource = CustomResource()

                @resource.create
                def on_create(event, ctx):
                    return {"x": "y"}

                replay = resource.replay(cfn_create_event, cfn_lambda_context)
                assert_success(replay, data={"x": "y"})


            def test_each_event_fixture_works(
                cfn_create_event,
                cfn_update_event,
                cfn_delete_event,
            ):
                assert cfn_create_event["RequestType"] == "Create"
                assert cfn_update_event["RequestType"] == "Update"
                assert cfn_delete_event["RequestType"] == "Delete"
                # PhysicalResourceId is required for Update/Delete.
                assert "PhysicalResourceId" in cfn_update_event
                assert "PhysicalResourceId" in cfn_delete_event
            """,
        ),
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Auto-discovered fixtures failed:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )


@pytest.mark.integration
def test_fixture_invocations_are_independent(tmp_path: Path) -> None:
    """Mutating one test's event must not bleed into a sibling."""
    test_file = tmp_path / "test_isolation.py"
    test_file.write_text(
        textwrap.dedent(
            """\
            def test_a_mutates(cfn_create_event):
                cfn_create_event["MUTATED"] = True

            def test_b_is_pristine(cfn_create_event):
                assert "MUTATED" not in cfn_create_event
            """,
        ),
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", str(test_file)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Fixture isolation failed:\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
