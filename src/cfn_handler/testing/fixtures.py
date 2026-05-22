"""pytest fixtures auto-loaded via the ``pytest11`` entry point.

This module is imported by pytest at collection time when ``cfn_handler``
is installed; it has no effect outside pytest. Importing this module
does not pull in pytest itself unless the fixtures are referenced.

Public fixtures:

- :func:`cfn_create_event`, :func:`cfn_update_event`, :func:`cfn_delete_event`:
  canonical CloudFormation custom-resource event dicts (one per request type).
- :func:`cfn_lambda_context`: a minimal ``LambdaContext``-protocol object.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from cfn_handler.testing._internal.context_factory import make_context
from cfn_handler.testing._internal.event_factory import make_event

if TYPE_CHECKING:
    from cfn_handler.resource import LambdaContext

# Stable values used by the Update/Delete fixtures so the PhysicalResourceId
# is consistent across calls. Tests that need uniqueness can override.
_FIXTURE_PHYSICAL_RESOURCE_ID = "test-physical-resource-id"


@pytest.fixture
def cfn_create_event() -> dict[str, Any]:
    """A canonical CloudFormation Create event dict.

    Returns a fresh dict on every test (mutations don't leak across tests).
    """
    return make_event(request_type="Create")


@pytest.fixture
def cfn_update_event() -> dict[str, Any]:
    """A canonical CloudFormation Update event dict.

    Includes a ``PhysicalResourceId`` (required by CFN for Update events)
    and an empty ``OldResourceProperties``. Tests can override either by
    mutating the returned dict.
    """
    return make_event(
        request_type="Update",
        physical_resource_id=_FIXTURE_PHYSICAL_RESOURCE_ID,
    )


@pytest.fixture
def cfn_delete_event() -> dict[str, Any]:
    """A canonical CloudFormation Delete event dict.

    Includes a ``PhysicalResourceId`` (required by CFN for Delete events).
    """
    return make_event(
        request_type="Delete",
        physical_resource_id=_FIXTURE_PHYSICAL_RESOURCE_ID,
    )


@pytest.fixture
def cfn_lambda_context() -> LambdaContext:
    """A minimal ``LambdaContext`` double satisfying the Protocol.

    Override fields by mutating the returned object, or call
    :func:`cfn_handler.testing.make_context` directly with kwargs.
    """
    return make_context()
