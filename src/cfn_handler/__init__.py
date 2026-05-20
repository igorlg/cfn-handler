"""Modern CloudFormation Custom Resource lifecycle handler for AWS Lambda.

Public API:
- :class:`CustomResource` — the entry point users instantiate.
- :class:`CfnHandlerError`, :class:`ResponseError` — exception hierarchy.

Everything under ``cfn_handler._internal`` is private implementation detail
and may change between minor versions.
"""

from importlib.metadata import PackageNotFoundError, version

from cfn_handler.exceptions import CfnHandlerError, ResponseError
from cfn_handler.resource import CustomResource

try:
    __version__ = version(__name__)
except PackageNotFoundError:  # pragma: no cover - only happens in unbuilt source trees
    __version__ = "0.0.0+unknown"

__all__ = [
    "CfnHandlerError",
    "CustomResource",
    "ResponseError",
    "__version__",
]
