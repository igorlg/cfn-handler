"""The runner that drives ``CustomResource.replay``.

Lives under ``cfn_handler.testing._internal`` (private). Splits the
``replay()`` logic out of ``resource.py`` to keep the production module
free of testing-only concerns.

The strategy: capture the resource's existing ``_transport``,
``_provision_poller``, and ``_teardown_poller`` attributes, swap them for
in-memory recorders, run a normal ``__call__``, then restore the originals.
The recorders also produce the ``Replay`` value returned to the caller.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from cfn_handler.testing._internal.replay_result import Replay, ReplayRequestType, ReplayStatus

if TYPE_CHECKING:
    from cfn_handler.resource import CustomResource, LambdaContext


def _make_default_context() -> LambdaContext:
    """Build a default context for ``replay()`` calls without an explicit one.

    Imported lazily because ``cfn_handler.testing._internal.context_factory``
    isn't part of the public API surface this module is documented as.
    """
    from cfn_handler.testing._internal.context_factory import make_context

    return make_context()


def run_replay(
    resource: CustomResource,
    event: dict[str, Any],
    context: LambdaContext | None,
) -> Replay:
    """Drive ``resource(event, context)`` with capturing transport + stub pollers.

    See :meth:`cfn_handler.CustomResource.replay` for the public contract.
    """
    if context is None:
        context = _make_default_context()

    request_type = cast("ReplayRequestType", event.get("RequestType", "Create"))

    # Capture state. Lists capture in mutation order; we only ever expect at
    # most one entry per call but allow more to surface bugs visibly.
    sent: list[dict[str, Any]] = []
    provisioned: list[bool] = []

    def capture_transport(_url: str, payload: dict[str, Any]) -> None:
        sent.append(payload)

    def stub_provision(
        evt: dict[str, Any],
        _function_name: str,
        _polling_interval_minutes: int = 1,
        _region: str | None = None,
    ) -> None:
        # Mirror real ``setup_polling`` event mutation so a follow-up
        # ``replay()`` of the mutated event correctly routes to the poll
        # handler. The marker values are syntactically valid placeholders;
        # tests that care about exact values can override via the public
        # poller seam (CustomResource(provision_poller=...)).
        evt["CfnHandlerPoll"] = True
        evt["CfnHandlerRule"] = "arn:aws:events:us-east-1:111111111111:rule/cfn-handler-replay-stub"
        evt["CfnHandlerPermission"] = "cfn-handler-replay-stub-permission"
        provisioned.append(True)

    def stub_teardown(
        _evt: dict[str, Any],
        _function_name: str,
        _region: str | None = None,
    ) -> None:
        # No-op: in replay we never set up real AWS resources, so there's
        # nothing to remove. Recording is unnecessary because the
        # post-poll terminal response in ``sent`` is the authoritative
        # signal that teardown was reached.
        return

    with resource._replay_seams(  # pyright: ignore[reportPrivateUsage]
        transport=capture_transport,
        provision_poller=stub_provision,
        teardown_poller=stub_teardown,
    ):
        resource(event, context)

    # Decide DEFERRED vs SUCCESS/FAILED based on what we captured.
    # If polling was provisioned AND no terminal response was emitted,
    # this was a deferral.
    if provisioned and not sent:
        return Replay(
            status="DEFERRED",
            physical_resource_id=None,
            data={},
            reason="",
            no_echo=False,
            payload={},
            request_type=request_type,
        )

    if not sent:
        # No response and no polling provisioned — should not happen on a
        # well-formed dispatch. Surface this as FAILED with a message
        # so test failures are loud, not silent.
        return Replay(
            status="FAILED",
            physical_resource_id=None,
            data={},
            reason="cfn-handler internal: dispatch produced no response and no polling deferral",
            no_echo=False,
            payload={},
            request_type=request_type,
        )

    payload = sent[-1]  # last response wins (a dispatch should only emit one)
    status: ReplayStatus = payload["Status"]
    return Replay(
        status=status,
        physical_resource_id=payload.get("PhysicalResourceId"),
        data=payload.get("Data", {}),
        reason=payload.get("Reason", ""),
        no_echo=payload.get("NoEcho", False),
        payload=payload,
        request_type=request_type,
    )
