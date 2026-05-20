"""Integration test using moto to mock CloudWatch Events and a real PUT endpoint.

This test exercises the full polling lifecycle:
1. Initial CREATE invocation runs the handler and provisions a CW Events rule.
2. We simulate the CW Events re-invocation by feeding the rule's stored event
   back into the resource as a poll-event.
3. The poll handler signals completion; the resource sends a SUCCESS response
   and tears down the rule.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import boto3
import pytest
from moto import mock_aws

from cfn_handler import CustomResource
from cfn_handler._internal.poller import EVENT_MARKER_RULE
from cfn_handler.resource import LambdaContext


@pytest.fixture
def moto_aws() -> Iterator[None]:
    with mock_aws():
        yield


@pytest.fixture
def fake_cfn_endpoint(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Capture every PUT to the simulated CFN ResponseURL for assertions.

    Returns the list of payloads (in order) that ``send_response`` would have
    PUT to CloudFormation.
    """
    captured: list[dict[str, Any]] = []

    class _FakeResponse:
        status = 200
        reason = "OK"

        def __enter__(self) -> _FakeResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def fake_urlopen(request: urllib.request.Request) -> _FakeResponse:
        # Capture the payload body.
        body = request.data
        if isinstance(body, bytes):
            captured.append(json.loads(body.decode("utf-8")))
        return _FakeResponse()

    monkeypatch.setattr(
        "cfn_handler._internal.response.urllib.request.urlopen",
        fake_urlopen,
    )
    return captured


@pytest.mark.integration
def test_create_with_polling_full_lifecycle(
    moto_aws: None,
    events: dict[str, dict[str, Any]],
    mock_context: Mock,
    fake_cfn_endpoint: list[dict[str, Any]],
) -> None:
    """End-to-end: CREATE -> setup polling -> poll re-invocation -> SUCCESS + teardown."""
    # Pre-create the Lambda function in moto so add_permission has a target.
    lambda_client = boto3.client("lambda", region_name="us-east-1")
    iam = boto3.client("iam", region_name="us-east-1")
    role = iam.create_role(
        RoleName="cfn-handler-test-role",
        AssumeRolePolicyDocument=json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "lambda.amazonaws.com"},
                        "Action": "sts:AssumeRole",
                    }
                ],
            }
        ),
    )
    lambda_client.create_function(
        FunctionName="test-function",
        Runtime="python3.12",
        Role=role["Role"]["Arn"],
        Handler="index.handler",
        Code={"ZipFile": b"def handler(event, context): pass"},
    )

    poll_called: list[bool] = []
    resource = CustomResource()

    @resource.create
    def on_create(_event: dict[str, Any], _context: LambdaContext) -> None:
        return None

    @resource.poll_create
    def on_poll(_event: dict[str, Any], _context: LambdaContext) -> dict[str, Any] | None:
        # First call: still running. Second call: done.
        if not poll_called:
            poll_called.append(True)
            return None
        return {"Endpoint": "https://my.example/done"}

    # ---- Initial invocation ---------------------------------------------
    create_event = events["Create"]
    resource(create_event, mock_context)

    # Should have provisioned a CW Events rule and NOT yet sent a CFN response.
    assert fake_cfn_endpoint == []
    events_client = boto3.client("events", region_name="us-east-1")
    rules = events_client.list_rules()["Rules"]
    assert len(rules) == 1
    assert EVENT_MARKER_RULE in create_event

    # ---- First poll re-invocation: still running ------------------------
    # CW Events would invoke the Lambda with the marker-augmented event.
    resource_2 = CustomResource()
    resource_2._lifecycle_handlers = resource._lifecycle_handlers  # share handlers
    resource_2._poll_handlers = resource._poll_handlers
    resource_2(create_event, mock_context)

    assert fake_cfn_endpoint == []  # still no terminal response
    assert events_client.list_rules()["Rules"]  # rule still in place

    # ---- Second poll re-invocation: completes ---------------------------
    resource_3 = CustomResource()
    resource_3._lifecycle_handlers = resource._lifecycle_handlers
    resource_3._poll_handlers = resource._poll_handlers
    resource_3(create_event, mock_context)

    # Now we expect a SUCCESS response and the rule torn down.
    assert len(fake_cfn_endpoint) == 1
    payload = fake_cfn_endpoint[0]
    assert payload["Status"] == "SUCCESS"
    assert payload["Data"] == {"Endpoint": "https://my.example/done"}
    assert events_client.list_rules()["Rules"] == []
