# error-handling Specification

## Purpose
TBD - created by archiving change bootstrap-v1-0-0. Update Purpose after archive.
## Requirements
### Requirement: Public exception hierarchy

The library SHALL expose a public exception hierarchy in `cfn_handler.exceptions`. The base class SHALL be `CfnHandlerError`. All library-specific exceptions SHALL be subclasses of `CfnHandlerError`. The base class and all public exception names SHALL be re-exported from the package root via `cfn_handler.__all__`.

#### Scenario: Base exception importable
- **WHEN** a user imports `from cfn_handler import CfnHandlerError`
- **THEN** the import succeeds and `CfnHandlerError` is a subclass of `Exception`

#### Scenario: Specific exceptions are subclasses
- **WHEN** any concrete library exception (e.g. `ResponseError`) is inspected
- **THEN** `issubclass(<exc>, CfnHandlerError)` is true

### Requirement: Response transmission failures are typed

The library SHALL define a `ResponseError` exception (a subclass of `CfnHandlerError`) raised internally when sending the response to `event["ResponseURL"]` fails (network failure, non-2xx HTTP status, etc.). This exception SHALL carry the original cause via standard exception chaining (`raise ResponseError(...) from cause`). The library MUST NOT swallow this exception silently — it SHALL be logged at ERROR level with full traceback before the Lambda returns.

#### Scenario: Response endpoint returns 500
- **WHEN** the HTTP PUT to `ResponseURL` returns status 500
- **THEN** a `ResponseError` is raised internally and logged at ERROR level

#### Scenario: Network error contacting response endpoint
- **WHEN** the HTTP PUT to `ResponseURL` raises `urllib.error.URLError`
- **THEN** a `ResponseError` is raised internally and chained from the `URLError` via `__cause__`

### Requirement: Handler exceptions become CloudFormation FAILED responses

When a user's lifecycle or poll handler raises any exception, the library SHALL catch it, send a `FAILED` response to CloudFormation with `Reason` derived from the exception's string form, and SHALL NOT re-raise from the Lambda entrypoint (so that AWS Lambda records the invocation as successful and CloudFormation receives the failure signal cleanly).

#### Scenario: Handler raises a custom exception
- **WHEN** a CREATE handler raises `MyAppError("policy not found")`
- **THEN** the FAILED response sent to CloudFormation has `Reason` containing `"policy not found"`, and the Lambda entrypoint returns normally (Lambda records SUCCESS)

#### Scenario: Handler raises an exception with empty message
- **WHEN** a handler raises `Exception()` (no message)
- **THEN** the FAILED response includes a non-empty `Reason` with the exception class name, ensuring CloudFormation has a parseable failure reason

### Requirement: Reason length is bounded

CloudFormation truncates response `Reason` fields at a known limit (currently 4096 characters). The library SHALL truncate `Reason` strings to fit within this limit, appending an ellipsis (`"..."`) when truncation occurs, before sending the response. Truncation SHALL preserve the most recent / most informative content (typically the exception message and last frames of the traceback when traceback is included).

#### Scenario: Reason fits within limit
- **WHEN** the failure reason is 100 characters
- **THEN** the response `Reason` field equals the original reason without modification

#### Scenario: Reason exceeds limit
- **WHEN** the failure reason is 5000 characters
- **THEN** the response `Reason` field is at most 4096 characters and ends with `"..."`

### Requirement: Init-time failures send FAILED response with diagnostics

If an exception is raised during `CustomResource` instantiation or at module-import time before any handler can run, the library SHALL still attempt to send a FAILED response when a CloudFormation event is later received, including a reason that mentions the init-time error and (where possible) the originating module/file. This ensures CloudFormation does not hang waiting on a response from a Lambda that failed before becoming responsive.

#### Scenario: Module-level error during cold start
- **WHEN** the user's Lambda code raises during import (before `CustomResource` is fully constructed) and a CFN event is received
- **THEN** a FAILED response is sent referencing the init-time error

### Requirement: Logging surface for diagnostics

The library SHALL log at INFO level on dispatch (`Received <RequestType> for <LogicalResourceId>`), at ERROR level for any exception caught from a handler (with full traceback), and at DEBUG level for response payloads (which may contain sensitive `Data`). The library SHALL use a logger named `cfn_handler` and SHALL NOT add handlers, formatters, or filters by default — log configuration is the user's responsibility, consistent with library best practices.

#### Scenario: Library does not configure root logger
- **WHEN** the library is imported into a Lambda function with default logging
- **THEN** the root logger configuration is unchanged (no handlers added, no level set)

#### Scenario: Caught handler exception is logged
- **WHEN** a registered handler raises an exception
- **THEN** the `cfn_handler` logger receives a record at ERROR level with the exception attached (so user log handlers see the traceback)

