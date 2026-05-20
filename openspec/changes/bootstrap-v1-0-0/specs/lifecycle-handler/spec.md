# Spec: lifecycle-handler

## ADDED Requirements

### Requirement: Public entry point class

The library SHALL expose a single public class `CustomResource` importable as `from cfn_handler import CustomResource`. This class SHALL be the only object users instantiate to define a CloudFormation custom resource handler.

#### Scenario: Importable from package root
- **WHEN** a user imports `from cfn_handler import CustomResource`
- **THEN** the import succeeds and `CustomResource` is a class

#### Scenario: Class is in `__all__`
- **WHEN** the user runs `from cfn_handler import *`
- **THEN** `CustomResource` is bound in the importing namespace

### Requirement: Lifecycle handler registration via decorators

`CustomResource` SHALL support registering handler callables for CloudFormation lifecycle events (`Create`, `Update`, `Delete`) via decorators named `create`, `update`, and `delete`. Each decorator MUST accept exactly one callable, MUST return that callable unchanged, and MUST raise `ValueError` if the same decorator is applied more than once on the same `CustomResource` instance.

#### Scenario: Decorator registers a handler
- **WHEN** the user applies `@resource.create` to a function `def fn(event, context): ...`
- **THEN** the function is registered as the CREATE handler and the decorator returns the original function

#### Scenario: Double registration is rejected
- **WHEN** the user applies `@resource.create` twice
- **THEN** the second application raises `ValueError`

### Requirement: Lambda entrypoint dispatches by RequestType

`CustomResource` instances SHALL be callable. When invoked with a CloudFormation custom-resource event and a Lambda context, the instance SHALL dispatch to the registered handler matching `event["RequestType"]`. Supported `RequestType` values are exactly `"Create"`, `"Update"`, and `"Delete"`.

#### Scenario: Create event invokes the create handler
- **WHEN** the instance is called with `event["RequestType"] == "Create"` and a CREATE handler is registered
- **THEN** the CREATE handler is invoked once with `(event, context)` as positional arguments

#### Scenario: Unknown request type fails the resource
- **WHEN** the instance is called with `event["RequestType"] == "FooBar"`
- **THEN** the resource is reported as `FAILED` to CloudFormation with a reason mentioning the unknown request type

#### Scenario: Missing handler for a known request type fails the resource
- **WHEN** the instance receives a `Delete` event but no DELETE handler is registered
- **THEN** the resource is reported as `FAILED` with a reason indicating no handler is registered

### Requirement: Successful handler completion reports SUCCESS

When a registered handler returns normally without registering a poll handler, `CustomResource` SHALL send a `SUCCESS` response to the CloudFormation `ResponseURL` and SHALL include the value returned by the handler as `Data` (response data) when that value is a `dict`, or no `Data` when the return value is `None`.

#### Scenario: Handler returns a dict
- **WHEN** the CREATE handler returns `{"Endpoint": "https://x.example"}`
- **THEN** the response payload sent to `ResponseURL` has `Status="SUCCESS"` and `Data={"Endpoint": "https://x.example"}`

#### Scenario: Handler returns None
- **WHEN** the DELETE handler returns `None`
- **THEN** the response payload sent to `ResponseURL` has `Status="SUCCESS"` and omits or sets `Data` to `{}`

### Requirement: Unhandled handler exceptions report FAILED

If a registered handler raises any exception that is not specifically handled by polling logic (see `polling` capability), `CustomResource` SHALL catch the exception and send a `FAILED` response to CloudFormation with `Reason` set to the string form of the exception.

#### Scenario: Handler raises a generic exception
- **WHEN** the CREATE handler raises `RuntimeError("boom")`
- **THEN** the response payload sent to `ResponseURL` has `Status="FAILED"` and `Reason` contains `"boom"`

### Requirement: PhysicalResourceId is determined per request type

`CustomResource` SHALL include `PhysicalResourceId` in every response according to these rules: for `Create`, the value MUST be either explicitly set by the handler (via assignment to a documented attribute) or default to a stable string derived from `event["LogicalResourceId"]` and `context.aws_request_id`. For `Update` and `Delete`, the value MUST default to the `PhysicalResourceId` carried in the incoming event but MAY be overridden by the handler (which signals replacement on `Update`).

#### Scenario: Create with no override generates a stable id
- **WHEN** the CREATE handler completes without setting `physical_resource_id`
- **THEN** the response includes a non-empty `PhysicalResourceId` derived deterministically from `LogicalResourceId` and `aws_request_id`

#### Scenario: Update echoes the existing PhysicalResourceId
- **WHEN** the UPDATE handler completes without setting `physical_resource_id` and the incoming event has `PhysicalResourceId="abc-123"`
- **THEN** the response includes `PhysicalResourceId="abc-123"`

#### Scenario: Update overrides the PhysicalResourceId (replacement)
- **WHEN** the UPDATE handler sets `physical_resource_id` to `"new-id"` (different from the incoming event)
- **THEN** the response includes `PhysicalResourceId="new-id"` (signalling replacement to CloudFormation)

### Requirement: NoEcho flag is supported per response

`CustomResource` SHALL include `NoEcho` in the response when the handler explicitly opts in. The default SHALL be omitted (which CloudFormation interprets as `false`).

#### Scenario: Handler enables NoEcho
- **WHEN** the handler sets `no_echo = True` before completing
- **THEN** the response payload includes `"NoEcho": true`

### Requirement: Response is sent via HTTP PUT to ResponseURL

`CustomResource` SHALL send the response payload as a JSON body via HTTP PUT to the URL provided by `event["ResponseURL"]`. The library MUST use the Python standard library `urllib` (no third-party HTTP client) to keep zero runtime dependencies.

#### Scenario: PUT is performed with the JSON body
- **WHEN** any handler completes
- **THEN** exactly one HTTP `PUT` request is issued to `event["ResponseURL"]` with `Content-Type: ""` (per CFN signed-URL contract) and a body that is the JSON-encoded response payload

### Requirement: Final response always sent

`CustomResource` SHALL guarantee that exactly one response is sent to CloudFormation per invocation, even when handler code raises, registers a poll, or itself attempts to send a response. Multiple responses or no response SHALL be considered a defect.

#### Scenario: Handler raises before completing
- **WHEN** the handler raises an exception
- **THEN** exactly one response is sent (a FAILED response with the exception text)

#### Scenario: Handler completes without raising
- **WHEN** the handler returns normally
- **THEN** exactly one response is sent (a SUCCESS response)
