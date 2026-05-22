"""CloudFormation response payload construction and HTTP transport.

The CloudFormation custom-resource contract is documented at:
https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref-responses.html

Key facts:
- The response is sent as JSON via HTTP PUT to a presigned S3 URL.
- ``Content-Type`` MUST be empty (per the signed URL contract).
- ``Reason`` is truncated by CloudFormation at 4096 characters.
- A response is REQUIRED for every CFN-initiated invocation; not responding
  causes the stack to hang for up to an hour.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Final, Literal

from cfn_handler._internal.log import logger
from cfn_handler.exceptions import ResponseError

ResponseStatus = Literal["SUCCESS", "FAILED"]

#: A pluggable transport callable: takes ``(url, payload)`` and is responsible
#: for delivering the payload to ``url``. The production implementation is
#: :func:`send_response` (urllib PUT). Testing helpers swap this for an
#: in-memory capture; see :mod:`cfn_handler.testing`.
Transport = Callable[[str, dict[str, Any]], None]

#: CloudFormation truncates the response ``Reason`` field at this many bytes.
#: See: https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/crpg-ref-responses.html
MAX_REASON_LENGTH: Final = 4096

#: CFN signed URL contract requires an empty Content-Type header. Some
#: ``urllib`` versions reject ``""`` outright; passing the header but with
#: an empty value is accepted on every Python we support.
_HEADERS: Final[dict[str, str]] = {"Content-Type": ""}


def truncate_reason(reason: str, limit: int = MAX_REASON_LENGTH) -> str:
    """Return ``reason`` truncated to fit within CloudFormation's limit.

    Truncation preserves the most recent (most-informative) end of the
    string and appends ``"..."`` to signal that information was dropped.
    """
    if len(reason) <= limit:
        return reason
    ellipsis = "..."
    keep = limit - len(ellipsis)
    return reason[-keep:] + ellipsis


def build_response(
    *,
    status: ResponseStatus,
    physical_resource_id: str,
    stack_id: str,
    request_id: str,
    logical_resource_id: str,
    reason: str = "",
    data: dict[str, Any] | None = None,
    no_echo: bool = False,
) -> dict[str, Any]:
    """Construct a CloudFormation response payload.

    Returns a dict ready for ``json.dumps`` and HTTP PUT to the
    ``ResponseURL``. ``Reason`` is automatically truncated to fit within
    CloudFormation's 4096-character limit.
    """
    payload: dict[str, Any] = {
        "Status": status,
        "PhysicalResourceId": str(physical_resource_id),
        "StackId": stack_id,
        "RequestId": request_id,
        "LogicalResourceId": logical_resource_id,
        "Reason": truncate_reason(reason),
        "Data": data or {},
    }
    if no_echo:
        payload["NoEcho"] = True
    return payload


def send_response(response_url: str, payload: dict[str, Any]) -> None:
    """Send the response payload to CloudFormation via HTTP PUT.

    Raises:
        ResponseError: If JSON serialization fails, the network call raises,
            or the server returns a non-2xx status.

    The original cause is preserved via ``raise ... from cause`` so callers
    can inspect ``exc.__cause__``.
    """
    try:
        body = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError) as cause:
        raise ResponseError(f"Failed to JSON-encode response payload: {cause}") from cause

    logger.debug("Sending CloudFormation response to %s: %s", response_url, payload)
    request = urllib.request.Request(
        url=response_url,
        data=body,
        headers=_HEADERS,
        method="PUT",
    )

    try:
        with urllib.request.urlopen(request) as response:
            status_code = response.status
            if status_code < 200 or status_code >= 300:
                raise ResponseError(f"CloudFormation rejected response: HTTP {status_code} {response.reason}")
            logger.info("CloudFormation acknowledged response: HTTP %d", status_code)
    except urllib.error.HTTPError as cause:
        raise ResponseError(f"CloudFormation rejected response: HTTP {cause.code} {cause.reason}") from cause
    except urllib.error.URLError as cause:
        raise ResponseError(f"Failed to reach CloudFormation response URL: {cause}") from cause
