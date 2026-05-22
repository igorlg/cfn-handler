# testing-helpers Specification (delta)

## ADDED Requirements

### Requirement: Public testing module is importable

The library SHALL expose a `cfn_handler.testing` module importable in any Python environment where `cfn_handler` itself imports cleanly, without requiring `pytest`, `boto3`, or any other optional dependency.

#### Scenario: Module imports without pytest installed
- **WHEN** a user runs `import cfn_handler.testing` in an environment
  where pytest is not installed
- **THEN** the import succeeds and the public names (`Replay`,
  `make_event`, `assert_success`, `assert_failed`, `assert_deferred`)
  are available

#### Scenario: Module imports without boto3 installed
- **WHEN** a user runs `import cfn_handler.testing` in an environment
  where boto3 is not installed
- **THEN** the import succeeds and `Replay` / `make_event` / assertion
  helpers are available

### Requirement: In-process replay of the dispatch flow

`CustomResource` SHALL expose a `replay(event, context=None)` method that executes the full dispatch pipeline in-process and returns a `Replay` object capturing the outcome, without issuing HTTP requests, importing `boto3`, or mutating the registered handler functions.

#### Scenario: Successful create handler is replayed
- **WHEN** a `CustomResource` has a CREATE handler registered that
  returns `{"Endpoint": "https://x"}`, and `replay(create_event)` is
  invoked
- **THEN** the returned `Replay` has `status="SUCCESS"`,
  `data={"Endpoint": "https://x"}`, and `payload` is the rendered
  CFN response payload that would have been PUT to the response URL

#### Scenario: Handler raises during replay
- **WHEN** a CREATE handler raises `RuntimeError("boom")` during
  replay
- **THEN** the returned `Replay` has `status="FAILED"` and `reason`
  contains `"boom"`

#### Scenario: Replay does not perform HTTP I/O
- **WHEN** `replay()` is invoked with a valid event whose `ResponseURL`
  is `https://example.invalid/cfn-response`
- **THEN** no HTTP request is made to any URL during the call

#### Scenario: Replay does not import boto3
- **WHEN** `replay()` is invoked in an environment without boto3
  installed AND no poll handler is registered
- **THEN** the call completes successfully without raising
  `PollingDependencyError` or `ImportError`

### Requirement: Replay produces a structured result

The `Replay` type SHALL be a frozen, immutable dataclass with the fields `status` (literal `"SUCCESS" | "FAILED" | "DEFERRED"`), `physical_resource_id` (`str | None`), `data` (`dict[str, Any]`), `reason` (`str`), `no_echo` (`bool`), `payload` (`dict[str, Any]`), and `request_type` (literal `"Create" | "Update" | "Delete"`).

#### Scenario: Replay result is immutable
- **WHEN** a user attempts to mutate `replay.status = "FAILED"` after
  a SUCCESS replay
- **THEN** `dataclasses.FrozenInstanceError` is raised

#### Scenario: Replay payload matches what would be sent
- **WHEN** `replay()` returns a `Replay` with `status="SUCCESS"` and
  `data={"Endpoint": "x"}`
- **THEN** `replay.payload["Status"] == "SUCCESS"`,
  `replay.payload["Data"] == {"Endpoint": "x"}`, and the payload
  conforms to the CFN custom-resource response schema

### Requirement: Replay supports the polling-deferral case

`replay()` SHALL handle the polling-deferral path without invoking any AWS API or importing `boto3`: when a matching poll handler is registered, it MUST return a `Replay` with `status="DEFERRED"` and an empty `payload` dict, and MUST mutate the input event to add the polling marker keys (`CfnHandlerPoll`, `CfnHandlerRule`, `CfnHandlerPermission`) so a subsequent `replay()` call resumes into the poll handler path.

#### Scenario: Create with poller defers
- **WHEN** a `CustomResource` has both `@create` and `@poll_create`
  handlers registered, and `replay(create_event)` is invoked
- **THEN** the returned `Replay` has `status="DEFERRED"`, no AWS API
  call is made, and the input event has been mutated to include
  `event["CfnHandlerPoll"] is True`

#### Scenario: Poll re-invocation completes the flow
- **WHEN** a deferred event is replayed a second time, and the
  registered poll handler returns response data
- **THEN** the returned `Replay` has `status="SUCCESS"` and the
  data the poll handler provided

### Requirement: Event factory produces canonical CFN events

The library SHALL expose a `make_event` callable in `cfn_handler.testing` that returns a dict matching the documented CloudFormation custom-resource event shape, with keyword overrides for every documented field, and MUST require a non-`None` `physical_resource_id` argument when `RequestType` is `"Update"` or `"Delete"` (raising `ValueError` if not supplied).

#### Scenario: Default Create event is well-formed
- **WHEN** `make_event()` is called with no arguments
- **THEN** the returned dict has `RequestType="Create"`,
  syntactically valid `StackId`, `RequestId`, `LogicalResourceId`,
  `ResourceType`, `ResourceProperties`, `ResponseURL`, `ServiceToken`
  fields, and no `PhysicalResourceId`

#### Scenario: Update event requires PhysicalResourceId
- **WHEN** `make_event(request_type="Update")` is called without
  passing `physical_resource_id`
- **THEN** `ValueError` is raised with a message identifying the
  missing argument

#### Scenario: Field overrides are applied
- **WHEN** `make_event(resource_properties={"Foo": "bar"})` is
  called
- **THEN** the returned dict has `ResourceProperties == {"Foo": "bar"}`

#### Scenario: Defaults use safe placeholder values
- **WHEN** `make_event()` is called with no overrides
- **THEN** the `ResponseURL` host is `example.invalid` (RFC 6761
  reserved name guaranteed not to resolve) and the account ID portion
  of `StackId` is `111111111111` (AWS-reserved example account)

### Requirement: Lambda context factory satisfies the protocol

The library SHALL expose a `make_context` callable in `cfn_handler.testing` that returns an object satisfying the existing `LambdaContext` protocol used by `CustomResource.__call__`, exposing `aws_request_id`, `function_name`, `invoked_function_arn`, `log_group_name`, `log_stream_name`, and `get_remaining_time_in_millis()`.

#### Scenario: Context satisfies the protocol
- **WHEN** `ctx = make_context()` is called and used in
  `resource.replay(event, ctx)`
- **THEN** the call succeeds and `ctx.get_remaining_time_in_millis()`
  returns a positive integer

#### Scenario: Remaining-time override is honoured
- **WHEN** `make_context(remaining_time_ms=5000)` is called
- **THEN** `ctx.get_remaining_time_in_millis()` returns `5000`

### Requirement: Assertion helpers raise informative AssertionError

The library SHALL expose `assert_success`, `assert_failed`, and `assert_deferred` helpers in `cfn_handler.testing`, each of which MUST raise `AssertionError` with a message identifying both the expected and actual values when the assertion fails.

#### Scenario: assert_success on a SUCCESS replay passes
- **WHEN** `assert_success(replay, data={"x": 1})` is called and
  `replay.status == "SUCCESS"` and `replay.data == {"x": 1}`
- **THEN** the call returns `None` (no exception)

#### Scenario: assert_success on a FAILED replay raises
- **WHEN** `assert_success(replay)` is called and
  `replay.status == "FAILED"` with `reason="boom"`
- **THEN** `AssertionError` is raised and the message contains both
  `"FAILED"` and `"boom"`

#### Scenario: assert_failed with reason_contains matches a substring
- **WHEN** `assert_failed(replay, reason_contains="boom")` is called
  and `replay.status == "FAILED"` with `reason="something boom happened"`
- **THEN** the call returns `None`

#### Scenario: assert_deferred on a SUCCESS replay raises
- **WHEN** `assert_deferred(replay)` is called and
  `replay.status == "SUCCESS"`
- **THEN** `AssertionError` is raised

### Requirement: pytest fixtures auto-register via entry point

The library's `pyproject.toml` SHALL declare a `pytest11` entry point named `cfn_handler` pointing at the fixtures module so that the fixtures `cfn_create_event`, `cfn_update_event`, `cfn_delete_event`, and `cfn_lambda_context` are available without any user-side `pytest_plugins` declaration.

#### Scenario: Fixture is auto-discovered
- **WHEN** a user with `cfn_handler` installed writes a test
  `def test_x(cfn_create_event): ...` in a fresh pytest project
  with no `conftest.py` configuration
- **THEN** pytest resolves the fixture without error and passes a
  Create-shaped event dict

#### Scenario: Each invocation gets a fresh event
- **WHEN** two tests both consume `cfn_create_event` and one mutates
  the event dict
- **THEN** the second test sees the unmutated default event (no
  cross-test leak)

### Requirement: Replay never sends a real CFN response

`CustomResource.replay` SHALL NOT, under any code path, send an HTTP request to the event's `ResponseURL` or any other URL, and the production HTTP transport MUST be replaced by an in-memory capture for the duration of the replay call and restored when the call returns or raises.

#### Scenario: Replay catches a handler exception without sending HTTP
- **WHEN** `replay()` is invoked with a handler that raises during
  execution
- **THEN** the returned `Replay` has `status="FAILED"` AND no HTTP
  request was issued (verified via mock or instrumentation)

#### Scenario: Replay restores transport after exception
- **WHEN** `replay()` raises an unexpected internal exception (not a
  handler exception) and the same `CustomResource` instance is then
  invoked normally via `__call__` (with the production HTTP transport)
- **THEN** the production invocation correctly issues an HTTP PUT to
  the event's `ResponseURL`
