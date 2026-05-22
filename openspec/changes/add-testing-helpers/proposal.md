# Proposal: Add testing helpers

## Why

Users writing custom-resource handlers with `cfn-handler` currently have
no first-class way to unit-test their handler logic. The library
instantiates `CustomResource`, attaches decorated lifecycle handlers,
and invokes the handler from a Lambda entry-point — but every layer
below that (response serialisation, HTTP `PUT` to the CFN response URL,
polling re-invocation) is wired into the dispatch path. To test a
handler in isolation, users today must monkey-patch `urllib.request`,
mock `boto3` clients, or construct a synthetic event and ignore the
side-effects.

This is friction the library should absorb. Custom-resource handlers
are exactly the kind of code where unit tests pay dividends (rare
production invocations, painful to debug after the fact, easy to write
in isolation). Shipping testing helpers makes the TDD loop cheap and
matches the "testable architecture is better architecture" stance the
project already adopts internally.

It's also a differentiator: `crhelper` (the upstream library this project
clean-roomed) ships nothing of the sort.

## What Changes

- **Add `CustomResource.replay(event, context=None)` method** that runs
  the dispatch logic in-process, intercepts the response payload before
  it would be sent to CloudFormation, and returns a structured `Replay`
  result. No HTTP, no boto3 lazy-import, no polling re-invocation.
- **Add a `cfn_handler.testing` module** exposing:
  - `Replay` (dataclass): captures `status`, `physical_resource_id`,
    `data`, `reason`, `no_echo`, plus the rendered response payload.
  - `make_event(...)`: factory returning a canonical
    CloudFormation custom-resource event dict, with sensible defaults
    that match the CFN documented event shape. Supports overriding
    any field.
  - `make_context(...)`: factory returning a minimal object that
    satisfies the `LambdaContext` protocol (`aws_request_id`,
    `function_name`, `invoked_function_arn`, `get_remaining_time_in_millis`,
    `log_group_name`, `log_stream_name`).
  - `assert_success(replay, *, data=None, physical_resource_id=None)`
    and `assert_failed(replay, *, reason_contains=None)` helpers.
- **Expose `cfn_handler.testing` in `__all__`** at package root via
  re-export of the public names from the new module. The test
  surface is part of the public API contract.
- **Add pytest fixtures** in `cfn_handler.testing.fixtures` that pytest
  auto-discovers via the `pytest11` entry point: `cfn_create_event`,
  `cfn_update_event`, `cfn_delete_event`, `cfn_lambda_context`. Users
  who don't use pytest are unaffected (entry point only loads in pytest
  collection).
- Polling-aware behaviour: when a poll handler is registered AND the
  initial dispatch would normally defer the response, `replay()` returns
  a `Replay` whose status is the sentinel `"DEFERRED"` (not a CFN value)
  to make it explicit. Subsequent `replay()` calls with the polling
  re-invocation event resume the flow.
- **Soft-deprecate the existing `test_mode` flag and `last_response`
  attribute** on `CustomResource`. Both keep working in v1.3 (no
  breaking change), but emit a `DeprecationWarning` directing users to
  the new `replay()` API. Earmarked for removal in v2.0 alongside
  other planned breaking changes.
- Migrate the existing internal test suite (~50 sites using
  `test_mode=True` and `last_response`) onto the new `replay()` API
  as part of this change. Dogfooding validates the new helpers under
  their real intended usage.

## Capabilities

### New Capabilities
- `testing-helpers`: in-process replay of the dispatch flow plus
  fixture/factory helpers that let users unit-test handlers without
  HTTP transport, AWS API calls, or moto.

### Modified Capabilities

None. The testing-helpers capability stands alone: it describes the
external behaviour of `replay()` and the testing surface. The internal
seam in the dispatch path that makes replay possible is an
implementation detail, captured in `design.md`, not in the existing
capability specs. Production behaviour of `lifecycle-handler` and
`polling` is unchanged: real Lambda invocations still send via HTTP
PUT, polling still provisions EventBridge rules.

## Impact

- **New module**: `src/cfn_handler/testing/` (importable as
  `cfn_handler.testing`). Privacy convention follows the rest of the
  package: testing surfaces are public; their internal helpers live in
  `cfn_handler/testing/_internal/`.
- **Package metadata**: a `pytest11` entry point is added to
  `pyproject.toml` for fixture auto-discovery. This does not add a
  runtime dependency on pytest; the entry point only fires inside
  pytest collection.
- **Internals refactor**: the dispatch path in `resource.py` and the
  HTTP send in `_internal/response.py` will need a thin seam (likely a
  `transport` callable parameter, default = the existing
  `send_response`) to support interception without monkeypatching. This
  is a small refactor, kept private.
- **Coverage gate**: testing helpers themselves are subject to the same
  95% line+branch threshold as the rest of the library. The dogfooding
  loop is: rewrite the existing test suite to use the new helpers
  where they fit, validate the helpers under their real intended
  usage.
- **Docs**: `README.md` gains a "Testing" section. A new examples
  directory entry (`examples/testing/`) is candidate but not required
  for this change.
- **Zero new runtime dependencies.**
- **No breaking changes in v1.3**: existing `test_mode=True` /
  `last_response` continue to work, but emit a `DeprecationWarning`.
  The new `replay()` API is purely additive. The `test_mode` /
  `last_response` removal is scheduled for v2.0 (separate change).
- Targets release `1.3.0` (minor bump).
