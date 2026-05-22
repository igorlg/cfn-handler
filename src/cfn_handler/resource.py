"""The :class:`CustomResource` class — public entry point for the library.

A typical usage looks like::

    from cfn_handler import CustomResource

    resource = CustomResource()

    @resource.create
    def on_create(event, context):
        return {"Endpoint": "https://my.example.com"}

    @resource.update
    def on_update(event, context):
        return {"Endpoint": "https://my.example.com"}

    @resource.delete
    def on_delete(event, context):
        pass

    def handler(event, context):
        return resource(event, context)

For long-running operations, register additional poll handlers with
:meth:`CustomResource.poll_create`, :meth:`poll_update`, :meth:`poll_delete`.
The library will provision a CloudWatch Events rule to re-invoke the Lambda
on a fixed schedule until the poll handler signals completion.
"""

from __future__ import annotations

import secrets
import string
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Literal, Protocol

from cfn_handler._internal.log import logger
from cfn_handler._internal.poller import (
    EVENT_MARKER_PERMISSION,
    EVENT_MARKER_RULE,
    PollerProvision,
    PollerTeardown,
    is_poll_event,
    setup_polling,
    teardown_polling,
)
from cfn_handler._internal.response import (
    ResponseStatus,
    Transport,
    build_response,
    send_response,
)
from cfn_handler._internal.timing import (
    DEFAULT_SAFETY_MARGIN_MS,
    has_time_for_iteration,
)
from cfn_handler.exceptions import CfnHandlerError, ResponseError

if TYPE_CHECKING:
    from cfn_handler.testing._internal.replay_result import Replay

#: A user-registered handler returns a dict (becomes ``Data``) or ``None``.
HandlerResult = dict[str, Any] | None

#: User-registered handler signature.
HandlerFn = Callable[[dict[str, Any], "LambdaContext"], HandlerResult]

#: CloudFormation lifecycle request types we dispatch on.
RequestType = Literal["Create", "Update", "Delete"]
_REQUEST_TYPES: frozenset[str] = frozenset({"Create", "Update", "Delete"})


class LambdaContext(Protocol):
    """Structural typing for the AWS Lambda invocation context.

    We only require the attributes ``cfn_handler`` actually reads. Real
    Lambda contexts have many more fields; users passing test doubles need
    only satisfy this Protocol.

    See: https://docs.aws.amazon.com/lambda/latest/dg/python-context.html
    """

    aws_request_id: str
    function_name: str

    def get_remaining_time_in_millis(self) -> int:
        """Return the number of milliseconds left in the Lambda invocation."""
        ...  # pragma: no cover - Protocol method; never executed at runtime


class _DoubleRegistrationError(ValueError):
    """Raised when the same lifecycle decorator is applied twice."""


def _generate_physical_id(event: dict[str, Any], aws_request_id: str) -> str:
    """Build a deterministic-but-unique physical resource id for CREATE.

    Uses the stack short-id + logical resource id + a random tail to make
    the value unique across replacements within the same stack.
    """
    stack_short = event["StackId"].split("/")[1] if "/" in event["StackId"] else event["StackId"]
    suffix = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    return f"{stack_short}-{event['LogicalResourceId']}-{suffix}-{aws_request_id[:8]}"


class CustomResource:
    """A CloudFormation Custom Resource lifecycle handler.

    Instantiate once at module load and register handlers via decorators.
    Call the instance from the Lambda entrypoint with ``(event, context)``.

    Args:
        polling_interval_minutes: Re-invocation cadence for polled resources.
            CloudWatch Events rules support a minimum of 1 minute.
        polling_safety_margin_ms: Time reserved at the end of a poll
            invocation for cleanup and response sending. If less remains,
            the resource is failed with a timeout reason rather than risk
            an unresponsive Lambda.
        test_mode: When True, responses are captured on
            :attr:`last_response` instead of being sent to CloudFormation.
            Useful for unit-testing handlers in isolation.
        transport: Optional transport callable replacing the default urllib
            PUT to the CFN response URL. Signature: ``(url, payload) -> None``.
            Used internally by :meth:`replay` and available for advanced
            users who need to interpose on the response. Pass ``None``
            (default) to use the production HTTP transport.
        provision_poller: Optional callable replacing the default
            ``setup_polling`` (boto3 EventBridge call) used when a
            polling handler is registered. Signature:
            ``(event, function_name, polling_interval_minutes, region) -> None``.
            Used internally by :meth:`replay` to stub out AWS calls.
        teardown_poller: Optional callable replacing the default
            ``teardown_polling``. Signature:
            ``(event, function_name, region) -> None``.
        log_level: Optional log level (``"DEBUG"``, ``logging.INFO``, etc.)
            to apply to the ``cfn_handler`` logger. Pass ``None`` (default)
            to leave the user's logging configuration alone.

    Attributes:
        physical_resource_id: User-overridable physical resource id. Set
            from inside a handler to force CloudFormation to treat the
            update as a replacement, or to provide a meaningful id on
            create (otherwise one is auto-generated).
        no_echo: When True, the ``Data`` field is masked in CloudFormation
            output (used for credentials).
        last_response: In ``test_mode``, the most recent response payload
            that *would* have been sent. ``None`` outside test mode.
    """

    physical_resource_id: str
    no_echo: bool
    last_response: dict[str, Any] | None

    def __init__(
        self,
        *,
        polling_interval_minutes: int = 1,
        polling_safety_margin_ms: int = DEFAULT_SAFETY_MARGIN_MS,
        test_mode: bool = False,
        transport: Transport | None = None,
        provision_poller: PollerProvision | None = None,
        teardown_poller: PollerTeardown | None = None,
        log_level: int | str | None = None,
    ) -> None:
        """Initialise the resource. Raises no exceptions; init failures should be reported via :meth:`init_failure`."""
        self._polling_interval_minutes = polling_interval_minutes
        self._polling_safety_margin_ms = polling_safety_margin_ms
        self._test_mode = test_mode
        # Default transport is the production HTTP PUT (looked up lazily in
        # ``_emit_response`` so that monkey-patching ``cfn_handler.resource.
        # send_response`` continues to work). Tests that want explicit
        # control inject a callable via the ``transport=`` kwarg or via
        # ``replay()``.
        self._transport: Transport | None = transport
        # Same late-binding pattern for poller seams: defaults are looked
        # up lazily so existing tests that ``patch("cfn_handler.resource.
        # setup_polling")`` continue to work; explicit kwargs short-circuit.
        self._provision_poller: PollerProvision | None = provision_poller
        self._teardown_poller: PollerTeardown | None = teardown_poller

        if log_level is not None:
            logger.setLevel(log_level)

        # Handler maps; populated via decorators.
        self._lifecycle_handlers: dict[str, HandlerFn] = {}
        self._poll_handlers: dict[str, HandlerFn] = {}

        # Per-invocation overridable state.
        self.physical_resource_id = ""
        self.no_echo = False
        self.last_response = None

        # Sticky init-failure marker. If set, every subsequent invocation
        # immediately reports FAILED. See #7/#67.
        self._init_error: BaseException | None = None

    # ---- Decorator API ---------------------------------------------------

    def _register_lifecycle(self, request_type: RequestType, fn: HandlerFn) -> HandlerFn:
        if request_type in self._lifecycle_handlers:
            msg = f"{request_type.lower()} handler is already registered on this CustomResource"
            raise _DoubleRegistrationError(msg)
        self._lifecycle_handlers[request_type] = fn
        return fn

    def _register_poll(self, request_type: RequestType, fn: HandlerFn) -> HandlerFn:
        if request_type in self._poll_handlers:
            msg = f"poll_{request_type.lower()} handler is already registered on this CustomResource"
            raise _DoubleRegistrationError(msg)
        self._poll_handlers[request_type] = fn
        return fn

    def create(self, fn: HandlerFn) -> HandlerFn:
        """Register the CREATE lifecycle handler."""
        return self._register_lifecycle("Create", fn)

    def update(self, fn: HandlerFn) -> HandlerFn:
        """Register the UPDATE lifecycle handler."""
        return self._register_lifecycle("Update", fn)

    def delete(self, fn: HandlerFn) -> HandlerFn:
        """Register the DELETE lifecycle handler."""
        return self._register_lifecycle("Delete", fn)

    def poll_create(self, fn: HandlerFn) -> HandlerFn:
        """Register the CREATE poll handler (for long-running creates)."""
        return self._register_poll("Create", fn)

    def poll_update(self, fn: HandlerFn) -> HandlerFn:
        """Register the UPDATE poll handler (for long-running updates)."""
        return self._register_poll("Update", fn)

    def poll_delete(self, fn: HandlerFn) -> HandlerFn:
        """Register the DELETE poll handler (for long-running deletes)."""
        return self._register_poll("Delete", fn)

    # ---- Init-failure escape hatch --------------------------------------

    def init_failure(self, error: BaseException) -> None:
        """Record a module-level / cold-start error.

        Once recorded, every subsequent call to ``self(event, context)``
        immediately sends a FAILED response to CloudFormation referencing
        the recorded error. This keeps CloudFormation from hanging when
        the user's setup code raised before any handler could run.
        """
        self._init_error = error
        logger.error("init_failure recorded: %s", error, exc_info=error)

    # ---- Lambda entrypoint ----------------------------------------------

    def __call__(self, event: dict[str, Any], context: LambdaContext) -> dict[str, Any] | None:
        """Dispatch the CFN event and ensure exactly one response is sent.

        Returns the captured response payload when ``test_mode=True``;
        returns ``None`` in production. The Lambda runtime ignores return
        values for custom resources, so this is purely a testing aid.
        """
        try:
            self._dispatch(event, context)
        except ResponseError:
            # Response transmission already logged inside send_response.
            # Don't crash the Lambda: re-raising here would mask the
            # original CFN-result intent.
            logger.exception("ResponseError caught at top level")
        except Exception:
            # Catastrophic backstop: dispatching itself raised. Best effort
            # to inform CloudFormation rather than letting the stack hang.
            logger.exception("Unhandled error in CustomResource.__call__")
            self._best_effort_failed(event, context, "Internal error in cfn_handler dispatch")
        return self.last_response if self._test_mode else None

    # ---- In-process replay (for testing) --------------------------------

    # ---- In-process replay (for testing) --------------------------------

    @contextmanager
    def _replay_seams(
        self,
        *,
        transport: Transport,
        provision_poller: PollerProvision,
        teardown_poller: PollerTeardown,
    ) -> Generator[None, None, None]:
        """Temporarily replace the production seams for a replay run.

        Internal contract used by ``cfn_handler.testing._internal.runner``.
        Snapshots the current values, swaps in the supplied callables,
        and restores on exit (including exceptions). Also forces
        ``test_mode`` off for the duration: ``replay()`` always wants
        the dispatch path to go through the supplied capturing
        transport, never the legacy ``last_response`` capture.
        """
        saved_transport = self._transport
        saved_provision = self._provision_poller
        saved_teardown = self._teardown_poller
        saved_test_mode = self._test_mode

        self._transport = transport
        self._provision_poller = provision_poller
        self._teardown_poller = teardown_poller
        self._test_mode = False

        try:
            yield
        finally:
            self._transport = saved_transport
            self._provision_poller = saved_provision
            self._teardown_poller = saved_teardown
            self._test_mode = saved_test_mode

    def replay(
        self,
        event: dict[str, Any],
        context: LambdaContext | None = None,
    ) -> Replay:
        """Execute the dispatch flow in-process and return a structured result.

        Replay runs the same code paths as :meth:`__call__` (handler
        resolution, handler invocation, polling deferral) but swaps the
        HTTP transport and the polling-provisioning callables for in-memory
        captures. No HTTP request is issued; ``boto3`` is never imported
        unless something on the user's handler path imports it.

        The same instance can be replayed multiple times. Each call
        snapshots the request type and rebuilds an isolated capture
        state, so polling-deferral tests work cleanly: replay once,
        observe ``status="DEFERRED"`` and the mutated event, replay
        again with the mutated event to drive the poll handler.

        Args:
            event: A CloudFormation custom-resource event. Use
                :func:`cfn_handler.testing.make_event` to build one.
            context: Optional Lambda context. Defaults to a fresh
                :func:`cfn_handler.testing.make_context` instance.

        Returns:
            A :class:`cfn_handler.testing.Replay` capturing the outcome.
        """
        # Local import to avoid a public→testing→public cycle at module load.
        from cfn_handler.testing._internal.runner import run_replay

        return run_replay(self, event, context)

    # ---- Internal dispatch ----------------------------------------------

    def _dispatch(self, event: dict[str, Any], context: LambdaContext) -> None:
        # Reset per-invocation state.
        self.last_response = None
        self.physical_resource_id = ""
        self.no_echo = False

        # Init-failure short-circuit.
        if self._init_error is not None:
            logger.error("init_failure flag set; sending FAILED")
            self._send_failed(event, context, str(self._init_error))
            return

        if is_poll_event(event):
            self._dispatch_poll(event, context)
        else:
            self._dispatch_lifecycle(event, context)

    def _dispatch_lifecycle(self, event: dict[str, Any], context: LambdaContext) -> None:
        request_type = event.get("RequestType")
        if request_type not in _REQUEST_TYPES:
            self._send_failed(event, context, f"Unknown RequestType: {request_type!r}")
            return

        handler = self._lifecycle_handlers.get(request_type)
        if handler is None:
            self._send_failed(event, context, f"No {request_type} handler is registered")
            return

        try:
            data = handler(event, context)
        except Exception as exc:
            logger.exception("Handler raised during %s", request_type)
            reason = self._reason_from_exception(exc)
            self._send_failed(event, context, reason)
            return

        # If a poll handler exists for this request type, switch to polling
        # mode: provision the CW Events rule and DO NOT send a response yet.
        if request_type in self._poll_handlers:
            self._enter_polling(event, context, data or {})
            return

        # No polling: send terminal SUCCESS now.
        self._send_success(event, context, data or {})

    def _dispatch_poll(self, event: dict[str, Any], context: LambdaContext) -> None:
        # We're being re-invoked by CloudWatch Events. The original event
        # payload (with our marker keys appended) is the input we get.
        request_type = event.get("RequestType")
        if request_type not in _REQUEST_TYPES:
            self._send_failed(event, context, f"Unknown RequestType in poll event: {request_type!r}")
            self._safe_teardown(event, context)
            return

        poll = self._poll_handlers.get(request_type)
        if poll is None:
            self._send_failed(event, context, f"No poll_{request_type.lower()} handler is registered")
            self._safe_teardown(event, context)
            return

        if not has_time_for_iteration(context, self._polling_safety_margin_ms):
            self._send_failed(event, context, "Polling timed out (insufficient Lambda time remaining)")
            self._safe_teardown(event, context)
            return

        # Echo the existing PhysicalResourceId across poll re-invocations.
        if "PhysicalResourceId" in event:
            self.physical_resource_id = event["PhysicalResourceId"]

        try:
            data = poll(event, context)
        except Exception as exc:
            logger.exception("Poll handler raised during %s", request_type)
            self._send_failed(event, context, self._reason_from_exception(exc))
            self._safe_teardown(event, context)
            return

        if data is None:
            # Continue polling: do nothing, leave the rule in place, return.
            logger.info("Poll continues for %s/%s", event.get("StackId"), event.get("LogicalResourceId"))
            return

        # Terminal SUCCESS from poller.
        self._send_success(event, context, data)
        self._safe_teardown(event, context)

    # ---- Polling provisioning -------------------------------------------

    def _enter_polling(
        self,
        event: dict[str, Any],
        context: LambdaContext,
        initial_data: dict[str, Any],
    ) -> None:
        """Provision the CW Events rule and exit without responding to CFN."""
        if self._test_mode:
            logger.info("test_mode: would provision polling rule, but skipping")
            # In test mode, simulate the deferred-response path by recording
            # a sentinel so tests can assert the resource intends to poll.
            self.last_response = {"__cfn_handler_polling__": True, "Data": initial_data}
            return

        try:
            provision = self._provision_poller if self._provision_poller is not None else setup_polling
            provision(event, context.function_name, self._polling_interval_minutes, None)
        except CfnHandlerError as exc:
            logger.exception("setup_polling failed; failing the resource")
            self._send_failed(event, context, self._reason_from_exception(exc))
            return
        logger.info("Lifecycle handler completed; polling rule installed; deferring CFN response")

    def _safe_teardown(self, event: dict[str, Any], context: LambdaContext) -> None:
        if self._test_mode:
            return
        if EVENT_MARKER_RULE not in event and EVENT_MARKER_PERMISSION not in event:
            return  # Nothing to tear down (initial invocation path that errored before setup).
        try:
            teardown = self._teardown_poller if self._teardown_poller is not None else teardown_polling
            teardown(event, context.function_name, None)
        except Exception:
            logger.exception("teardown_polling raised; continuing")

    # ---- Response building ---------------------------------------------

    def _send_success(
        self,
        event: dict[str, Any],
        context: LambdaContext,
        data: dict[str, Any],
    ) -> None:
        payload = self._build_payload(event, context, "SUCCESS", reason="", data=data)
        self._emit_response(event, payload)

    def _send_failed(
        self,
        event: dict[str, Any],
        context: LambdaContext,
        reason: str,
    ) -> None:
        payload = self._build_payload(event, context, "FAILED", reason=reason, data={})
        self._emit_response(event, payload)

    def _build_payload(
        self,
        event: dict[str, Any],
        context: LambdaContext,
        status: ResponseStatus,
        *,
        reason: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        return build_response(
            status=status,
            physical_resource_id=self._resolve_physical_id(event, context),
            stack_id=event.get("StackId", ""),
            request_id=event.get("RequestId", ""),
            logical_resource_id=event.get("LogicalResourceId", ""),
            reason=reason,
            data=data,
            no_echo=self.no_echo,
        )

    def _resolve_physical_id(self, event: dict[str, Any], context: LambdaContext) -> str:
        """Compute the PhysicalResourceId per request type.

        Precedence:
        1. ``self.physical_resource_id`` if set by the user (any request type).
        2. ``event["PhysicalResourceId"]`` if present (Update/Delete).
        3. Auto-generated stable id (Create, or anywhere we have no fallback).
        """
        if self.physical_resource_id:
            return self.physical_resource_id
        if "PhysicalResourceId" in event:
            return str(event["PhysicalResourceId"])
        return _generate_physical_id(event, context.aws_request_id)

    def _emit_response(self, event: dict[str, Any], payload: dict[str, Any]) -> None:
        if self._test_mode:
            self.last_response = payload
            logger.info("test_mode: skipping CFN response, captured on .last_response")
            return
        # Late-bound default: look up the module-level ``send_response`` at
        # call time so existing tests that monkey-patch
        # ``cfn_handler.resource.send_response`` continue to work. An
        # explicit ``transport=`` kwarg short-circuits this and is what
        # ``replay()`` uses to capture without HTTP.
        transport = self._transport if self._transport is not None else send_response
        try:
            transport(event["ResponseURL"], payload)
        except ResponseError:
            logger.exception("Failed to send CloudFormation response")

    def _best_effort_failed(
        self,
        event: dict[str, Any],
        context: LambdaContext,
        reason: str,
    ) -> None:
        """Last-ditch attempt to inform CFN after a catastrophic dispatch error."""
        try:
            self._send_failed(event, context, reason)
        except Exception:
            logger.exception("Best-effort FAILED response also failed")

    # ---- Helpers ---------------------------------------------------------

    @staticmethod
    def _reason_from_exception(exc: BaseException) -> str:
        text = str(exc)
        if not text:
            text = type(exc).__name__
        return text


# Re-export the double-registration error class with a clean public name for
# users who want to catch it specifically. It is not part of ``__all__`` at
# the top level because most users will catch the broader :class:`ValueError`.
DoubleRegistrationError = _DoubleRegistrationError
