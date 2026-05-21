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

### Requirement: Init-failure escape hatch via `init_failure(error)`

`CustomResource` SHALL expose an `init_failure(error)` method for users to record cold-start / module-load errors that they catch themselves. Once an error is recorded via `init_failure`, every subsequent invocation SHALL immediately send a FAILED response to CloudFormation referencing that error, without invoking any registered handler. This lets users whose module-level setup code can fail (database connections, secret retrieval, configuration parsing) wrap their setup in `try/except` and report the failure to CloudFormation cleanly rather than letting the Lambda hang.

NOTE: This requirement covers only failures the user explicitly catches and reports. If user code raises uncaught during module import, AWS Lambda's runtime fails to import the module and the handler is never invoked; the library has no opportunity to run, let alone respond. That scenario is between AWS Lambda's invocation lifecycle and CloudFormation's `ResponseURL` timeout (~1 hour), and is outside this library's contract. Users SHOULD wrap fallible setup code in `try/except` and route caught exceptions through `init_failure` to avoid this case.

#### Scenario: User catches setup failure and reports via init_failure
- **WHEN** the user catches a cold-start setup failure at module load (e.g. `try: db = connect_db() except Exception as e: resource.init_failure(e)`) and a CloudFormation event is later delivered
- **THEN** the library immediately sends a FAILED response with `Reason` derived from the recorded error, without invoking any registered handler

#### Scenario: User does not catch setup failure
- **WHEN** user setup code raises uncaught at module-import time
- **THEN** Lambda's runtime fails to import the module; no library code runs; no response is sent (out of scope; CloudFormation will eventually time out the resource)

### Requirement: Logging surface for diagnostics

The library SHALL log at INFO level on dispatch (`Received <RequestType> for <LogicalResourceId>`), at ERROR level for any exception caught from a handler (with full traceback), and at DEBUG level for response payloads (which may contain sensitive `Data`). The library SHALL use a logger named `cfn_handler` and SHALL NOT add handlers, formatters, or filters by default — log configuration is the user's responsibility, consistent with library best practices.

#### Scenario: Library does not configure root logger
- **WHEN** the library is imported into a Lambda function with default logging
- **THEN** the root logger configuration is unchanged (no handlers added, no level set)

#### Scenario: Caught handler exception is logged
- **WHEN** a registered handler raises an exception
- **THEN** the `cfn_handler` logger receives a record at ERROR level with the exception attached (so user log handlers see the traceback)

