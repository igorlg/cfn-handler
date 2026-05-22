"""Testing helpers for users writing custom-resource handlers with cfn-handler.

The public surface lives at :mod:`cfn_handler.testing`; do not import from
``cfn_handler.testing._internal`` (that subpackage is private and may
change between minor versions).

Quickstart::

    from cfn_handler import CustomResource
    from cfn_handler.testing import make_event, assert_success

    def test_my_handler():
        resource = CustomResource()

        @resource.create
        def on_create(event, ctx):
            return {"Endpoint": "https://x"}

        replay = resource.replay(make_event())
        assert_success(replay, data={"Endpoint": "https://x"})

The full public API is re-exported from this module's ``__all__``.
"""

from __future__ import annotations

from cfn_handler.testing._internal.assertions import (
    assert_deferred,
    assert_failed,
    assert_success,
)
from cfn_handler.testing._internal.context_factory import make_context
from cfn_handler.testing._internal.event_factory import make_event
from cfn_handler.testing._internal.replay_result import Replay

__all__ = [
    "Replay",
    "assert_deferred",
    "assert_failed",
    "assert_success",
    "make_context",
    "make_event",
]
