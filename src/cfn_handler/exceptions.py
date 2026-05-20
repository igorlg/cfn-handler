"""Public exception hierarchy for ``cfn_handler``.

All library-specific exceptions inherit from :class:`CfnHandlerError`. Catching
``CfnHandlerError`` will catch any exception raised by this library; catching
:class:`Exception` is also fine (the library never re-raises arbitrary user
exceptions from the Lambda entrypoint).
"""

from __future__ import annotations


class CfnHandlerError(Exception):
    """Base class for all ``cfn_handler`` exceptions.

    Subclass this rather than :class:`Exception` if you want to raise a
    library-specific error from your own code that interoperates with
    ``cfn_handler``'s error semantics.
    """


class ResponseError(CfnHandlerError):
    """Raised internally when the CloudFormation response cannot be sent.

    This wraps the underlying transport error (``urllib.error.URLError``,
    HTTP non-2xx status, JSON serialization failure, etc.) and chains it via
    standard exception chaining (``raise ... from <cause>``).

    The library logs this exception at ERROR level before the Lambda returns;
    user code does not need to catch it. Tests may assert on the chained
    cause via ``exc_info.value.__cause__``.
    """
