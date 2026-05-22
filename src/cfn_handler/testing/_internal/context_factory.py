"""Lambda context factory for tests.

The factory produces an object satisfying the
:class:`~cfn_handler.resource.LambdaContext` Protocol with sensible
defaults. Designed to be used directly (in non-pytest tests) or via the
:func:`cfn_handler.testing.fixtures.cfn_lambda_context` pytest fixture.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Default time remaining at the start of a fresh Lambda invocation.
#: 5 minutes is the AWS Lambda default for new functions.
DEFAULT_REMAINING_TIME_MS = 300_000


@dataclass
class _ReplayLambdaContext:
    """A plain dataclass that structurally satisfies ``LambdaContext``.

    Intentionally not a ``Mock`` so that mypy/pyright in user code see
    real attribute types (a ``Mock`` reports everything as ``Any``,
    defeating type checking).
    """

    aws_request_id: str = "00000000-0000-0000-0000-000000000000"
    function_name: str = "test-function"
    invoked_function_arn: str = "arn:aws:lambda:us-east-1:111111111111:function:test-function"
    log_group_name: str = "/aws/lambda/test-function"
    log_stream_name: str = "2026/05/22/[$LATEST]00000000000000000000000000000000"
    _remaining_time_ms: int = DEFAULT_REMAINING_TIME_MS

    def get_remaining_time_in_millis(self) -> int:
        """Return the configured remaining time, in milliseconds."""
        return self._remaining_time_ms


def make_context(
    *,
    aws_request_id: str = "00000000-0000-0000-0000-000000000000",
    function_name: str = "test-function",
    invoked_function_arn: str = "arn:aws:lambda:us-east-1:111111111111:function:test-function",
    log_group_name: str = "/aws/lambda/test-function",
    log_stream_name: str = "2026/05/22/[$LATEST]00000000000000000000000000000000",
    remaining_time_ms: int = DEFAULT_REMAINING_TIME_MS,
) -> _ReplayLambdaContext:
    """Build a Lambda context double satisfying the ``LambdaContext`` Protocol.

    All defaults use safe placeholder values (RFC 5737 / AWS-reserved
    example account ID ``111111111111``) so a misrouted test can't hit
    real infrastructure.

    Args:
        aws_request_id: Value for ``ctx.aws_request_id``.
        function_name: Value for ``ctx.function_name``.
        invoked_function_arn: Value for ``ctx.invoked_function_arn``.
        log_group_name: Value for ``ctx.log_group_name``.
        log_stream_name: Value for ``ctx.log_stream_name``.
        remaining_time_ms: Value returned by ``ctx.get_remaining_time_in_millis()``.

    Returns:
        A dataclass instance structurally compatible with ``LambdaContext``.
    """
    return _ReplayLambdaContext(
        aws_request_id=aws_request_id,
        function_name=function_name,
        invoked_function_arn=invoked_function_arn,
        log_group_name=log_group_name,
        log_stream_name=log_stream_name,
        _remaining_time_ms=remaining_time_ms,
    )
