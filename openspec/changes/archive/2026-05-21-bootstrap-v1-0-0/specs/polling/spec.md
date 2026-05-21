# Spec: polling

## ADDED Requirements

### Requirement: Poll handler registration via decorators

`CustomResource` SHALL support registering polling handlers for each lifecycle phase via decorators named `poll_create`, `poll_update`, and `poll_delete`. Each MUST accept exactly one callable, MUST return that callable unchanged, and MUST raise `ValueError` if the same decorator is applied more than once on the same instance.

#### Scenario: Poll decorator registers a poller
- **WHEN** the user applies `@resource.poll_create` to a function `def fn(event, context): ...`
- **THEN** the function is registered as the CREATE poller and the decorator returns the original function

#### Scenario: Double poll registration is rejected
- **WHEN** the user applies `@resource.poll_update` twice
- **THEN** the second application raises `ValueError`

### Requirement: Initial handler can defer to polling

When a lifecycle handler completes successfully and a matching poll handler is registered, `CustomResource` SHALL NOT send a final SUCCESS response. Instead it SHALL provision a CloudWatch Events rule that re-invokes the same Lambda function on a 1-minute schedule, then return without responding to CloudFormation. The CloudFormation response (SUCCESS or FAILED) SHALL be sent only after polling concludes.

#### Scenario: Create handler with poller registered defers response
- **WHEN** a CREATE handler completes and a `poll_create` handler is registered
- **THEN** no response is sent to CloudFormation, a CloudWatch Events rule is created, and the function returns normally

### Requirement: Polling re-invocations dispatch to the poll handler

When the Lambda is re-invoked via the CloudWatch Events rule provisioned during the initial call, `CustomResource` SHALL detect the polling re-invocation (by inspecting event content) and dispatch to the registered poll handler instead of the lifecycle handler.

#### Scenario: Re-invocation routes to poller
- **WHEN** the CloudWatch Events rule fires and the Lambda is re-invoked with the polling event payload
- **THEN** the registered poll handler is invoked with the original lifecycle event and the new Lambda context

### Requirement: Poll handler signals completion

A poll handler SHALL signal one of three outcomes per invocation: continue polling (return without raising and without setting a completion flag), success (set the completion flag and return), or failure (raise an exception). The exact API by which a poller signals "continue" SHALL be: do nothing — return without raising, without registering a final response. The API for "complete" SHALL be: register a final response payload (data dict for success, exception for failure).

#### Scenario: Poll returns without completing
- **WHEN** the poll handler returns normally and has not signalled completion
- **THEN** no CloudFormation response is sent and the CloudWatch Events rule remains in place

#### Scenario: Poll completes with success data
- **WHEN** the poll handler signals completion with response data `{"Endpoint": "https://x.example"}`
- **THEN** a SUCCESS response is sent to CloudFormation with that data and the CloudWatch Events rule is deleted

#### Scenario: Poll raises
- **WHEN** the poll handler raises `RuntimeError("operation failed")`
- **THEN** a FAILED response is sent with `Reason` containing `"operation failed"` and the CloudWatch Events rule is deleted

### Requirement: Polling respects Lambda time budget

Both lifecycle and poll handlers SHALL run within the Lambda execution time budget. `CustomResource` SHALL determine remaining time via `context.get_remaining_time_in_millis()` and SHALL leave a configurable safety margin (default 30 seconds) for cleanup and response sending. If the safety margin would be exceeded by continuing, `CustomResource` SHALL fail the resource with a timeout reason rather than risk an unresponsive Lambda.

#### Scenario: Sufficient time remaining
- **WHEN** a poll iteration starts and `get_remaining_time_in_millis()` returns 60000 (60s)
- **THEN** the poll handler is invoked normally

#### Scenario: Insufficient time remaining
- **WHEN** a poll iteration starts and `get_remaining_time_in_millis()` returns 5000 (5s, less than the 30s safety margin)
- **THEN** the resource is reported as FAILED with a reason indicating timeout, the CloudWatch Events rule is deleted, and the poll handler is NOT invoked

### Requirement: CloudWatch Events rule is cleaned up on terminal outcomes

`CustomResource` SHALL delete the CloudWatch Events rule (and any associated Lambda permissions/targets it created) whenever a terminal response (SUCCESS or FAILED) is sent on a polled flow. The rule MUST be deleted even when the response itself fails to send.

#### Scenario: Poll completes successfully
- **WHEN** a poll signals completion successfully
- **THEN** the CloudWatch Events rule is deleted before or immediately after the response is sent

#### Scenario: Poll fails
- **WHEN** a poll raises an exception
- **THEN** the CloudWatch Events rule is deleted before or immediately after the FAILED response is sent

### Requirement: Polling requires AWS SDK at runtime

Because polling provisions and tears down CloudWatch Events rules and Lambda permissions, polling SHALL require `boto3` to be available in the Lambda environment. The library itself MUST NOT add `boto3` as a hard runtime dependency (it is preinstalled in AWS Lambda Python runtimes), but SHALL raise a clear ImportError or library-specific error if polling is requested in an environment without `boto3`.

#### Scenario: Polling is registered but boto3 is unavailable
- **WHEN** the user registers a poll handler in an environment where `import boto3` fails
- **THEN** an error is raised at handler registration time (or at first invocation, whichever the design selects), with a message that explains polling requires `boto3`
