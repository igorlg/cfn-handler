# Design: Testing helpers

## Context

`cfn-handler`'s production dispatch path is well-defined and tested. The
public API surface is `CustomResource`, the lifecycle decorators
(`@create`, `@update`, `@delete`), and the polling decorators
(`@poll_create` etc.). When the user-decorated handler completes, the
library runs:

```
            ┌────────────────────────────────────────────┐
            │  CustomResource.__call__(event, context)   │
            └────────────────────────────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  resolve handler by  │
                   │     RequestType      │
                   └──────────────────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │  invoke user handler │
                   └──────────────────────┘
                              │
                ┌─────────────┴─────────────┐
                ▼                           ▼
       ┌────────────────┐           ┌──────────────────┐
       │ poll handler   │           │ no poll handler  │
       │ registered     │           │ registered       │
       │ → setup_polling│           │ → build_response │
       │   (boto3)      │           │ → send_response  │
       │ return early   │           │   (urllib PUT)   │
       └────────────────┘           └──────────────────┘
```

### Existing test surface — `test_mode` / `last_response`

The library already ships a rough first-pass at testing helpers:

- `CustomResource(test_mode=True)` — skips HTTP and skips polling
  provisioning/teardown.
- `self.last_response` — captures the response payload that would have
  been PUT to the CFN URL.
- For the polling-defer case, `last_response` gets a sentinel
  `{"__cfn_handler_polling__": True, "Data": ...}`.

This works for the basic SUCCESS/FAILED-payload assertions but has known
problems:

1. **Mutable state on the resource.** Tests must reset
   `last_response = None` between assertions or risk false positives.
2. **Sentinel string for polling.** `"__cfn_handler_polling__"` is a
   private-by-convention key but lives on the public `last_response`
   surface; it has no type, no documentation guarantees.
3. **Polling re-invocation can't be tested.** `test_mode` short-circuits
   `setup_polling` entirely, so the polling marker keys
   (`CfnHandlerPoll`, `CfnHandlerRule`, `CfnHandlerPermission`) are
   never added to the event. A test cannot then re-invoke `__call__`
   with the marked event to simulate the second dispatch (the
   marker-detection path expects those keys).
4. **Two ways to do everything.** Without a clear superseding API, the
   library accumulates testing surfaces.

The `replay()` API and `cfn_handler.testing` module supersede these.

### Test-mode migration strategy

This change ships in v1.3.0 alongside the new `replay()` API. To avoid
breaking existing users:

- `test_mode=True` keeps working in v1.3 with identical semantics.
- Constructing a `CustomResource(test_mode=True)` emits a
  `DeprecationWarning` pointing at `replay()`.
- Setting / reading `last_response` does NOT warn directly (would warn
  inside `_emit_response` on every test invocation; too noisy). The
  deprecation is signalled through the constructor only.
- The internal test suite migrates to `replay()` as part of this PR
  (~50 call-sites). This is mechanical and validates the new API.
- v2.0 (separate change, no timeline yet) removes `test_mode`,
  `last_response`, and the `__cfn_handler_polling__` sentinel.

To unit-test the user handler today, the user must:
1. Construct a synthetic event dict (no helper exists);
2. Construct a Lambda context object (no helper exists);
3. Patch `cfn_handler._internal.response.send_response` to intercept
   the PUT (relies on internal-module knowledge);
4. Patch `cfn_handler._internal.poller.setup_polling` if any poll handler
   is registered (relies on internal-module knowledge).

This is testable, but only by knowing the internals — which `_internal/`
explicitly says is unstable. A user who reaches into `_internal/`
shouldn't expect their tests to survive a minor-version bump.

The fix is to ship the test seam as a public surface.

## Goals / Non-Goals

**Goals:**

- Let users unit-test custom-resource handlers without HTTP, without
  boto3, and without reaching into `cfn_handler._internal/`.
- Provide canonical event/context factories so users don't reinvent
  fixture data.
- Provide assertion helpers that read naturally
  (`assert_success(replay, data={...})`).
- Auto-discover pytest fixtures via the `pytest11` entry point so users
  who already use pytest get fixtures for free without an explicit
  `pytest_plugins` declaration.
- Cover the polling case: `replay()` of an event that would defer to
  polling produces a `Replay` with status `"DEFERRED"`. Calling
  `replay()` again with the polling re-invocation event resumes the
  flow.
- Keep zero runtime dependencies. pytest is **not** a runtime dep; the
  fixture entry point is loaded only inside pytest collection.

**Non-Goals:**

- **Integration testing helpers.** Standing up moto, simulating EventBridge
  rule firing, and verifying that boto3 was called with specific args is
  out of scope. Users wanting that already have moto + the existing
  public API. We're not building a second integration-test stack.
- **Mocking the user's downstream calls.** The user is responsible for
  mocking their own SDK calls; that's not this library's concern.
- **A "fluent" or builder API for events.** `make_event(**overrides)` is
  enough; nobody needs `EventBuilder().with_request_type("Create")...`.
- **Fixtures for non-pytest test runners.** unittest users can call the
  factories directly — `cfn_create_event()` works in any context.

## Decisions

### D1. Public module: `cfn_handler.testing`

The testing surface lives in `src/cfn_handler/testing/__init__.py`,
re-exported from `cfn_handler.testing` (not from `cfn_handler` root).
Top-level imports remain minimal:

```python
import cfn_handler            # production code only
import cfn_handler.testing    # tests only
```

Rationale:
- Test code shouldn't accidentally land in production bundles. By
  partitioning the surface, the `cfn_handler.testing` module can be
  flagged in lint configs (e.g. `flake8-tidy-imports` ban-relative).
- Mirrors the layout used by other libraries (e.g. `httpx.testing`,
  `aiohttp.test_utils`).
- The Lambda Layer build can optionally exclude
  `cfn_handler/testing/` to keep the layer small (saves a few KB; not
  decisive).

**Rejected alternative**: re-exporting helpers from `cfn_handler` root.
Pollutes `__all__` with names that have no place in production. The
import discipline this enforces is worth a tiny extra keystroke.

### D2. `Replay` is a frozen dataclass, not a tuple or a class with logic

```python
@dataclass(frozen=True, slots=True)
class Replay:
    status: Literal["SUCCESS", "FAILED", "DEFERRED"]
    physical_resource_id: str | None
    data: dict[str, Any]
    reason: str
    no_echo: bool
    payload: dict[str, Any]   # the rendered response payload, or {} if DEFERRED
    request_type: Literal["Create", "Update", "Delete"]
```

Rationale:
- Immutable means tests can't accidentally mutate the result and
  confuse subsequent assertions.
- `slots=True` is a small memory win; mostly there for hygiene.
- `payload` is the full rendered response (what would have hit the
  CFN URL). Useful for tests that care about NoEcho or want to assert
  on the wire format directly.
- `"DEFERRED"` is a sentinel that does NOT exist in real CFN
  responses. Choosing a string means it survives equality comparison
  cleanly without users importing an enum.

**Rejected alternative**: an enum for `status`. `Literal` strings are
lighter, work with structural typing, and don't require an import
for users.

**Rejected alternative**: returning `None` for `payload` when DEFERRED.
Nullable fields force `if replay.payload is None` branches in tests.
An empty dict is a sentinel value with no information loss.

### D3. The dispatch seam: `transport` parameter

`CustomResource.__call__` and the polling deferral path both end up
calling `_internal.response.send_response(url, payload)`. To make
replay possible, we add a `transport` parameter to the internal
dispatch flow:

```python
# Internal type:
Transport = Callable[[str, dict[str, Any]], None]

# Default:
def _http_transport(url: str, payload: dict[str, Any]) -> None:
    send_response(url, payload)   # urllib PUT, existing behaviour

# CustomResource holds a transport, defaulting to _http_transport.
# replay() injects an "intercepting" transport that captures the
# (url, payload) tuple instead of sending it.
```

The same seam is used in the polling teardown path: when polling
completes, the final response goes through the same `transport`, so
replay-driven polling tests work identically.

**Why not monkeypatching?** Monkeypatching requires users to know what
to patch (`cfn_handler._internal.response.send_response` —
which `_internal/` says is unstable). The seam makes the dependency
inversion explicit and stable.

**Why a callable parameter rather than a `Protocol`?** Lower ceremony,
and the contract is genuinely a single function call. No need to
ship a `Transport(Protocol)` class users would have to implement.

**Why default to `_http_transport` rather than letting users pass
`send_response` themselves?** Backwards compatibility. The existing
`__init__` signature must keep working with no kwargs.

### D4. Polling without boto3

The polling setup/teardown path lazy-imports `boto3`. In replay mode
we never want to call boto3 at all, even with mocked clients —
that's the whole point. The intercepting transport paired with a
**stub poller** captures "would have called setup_polling with these
args" without actually importing boto3.

The stub poller follows the same Transport-like seam pattern:

```python
PollerProvision = Callable[[dict[str, Any], str, int, str | None], None]
PollerTeardown  = Callable[[dict[str, Any], str, str | None], None]

# Default: thin wrappers around _internal.poller functions.
# Replay: stubs that record the call and mutate `event` to add the
# polling marker keys (so the user can assert "would have polled").
```

When `replay()` is called and a poll handler is registered, the
returned `Replay` has `status="DEFERRED"`. The stub mutates the event
to add the polling markers (`CfnHandlerPoll`, `CfnHandlerRule`,
`CfnHandlerPermission`), so a follow-up `replay(event_with_markers)`
correctly routes to the poll handler.

**Rejected alternative**: requiring users to install boto3 + moto
to test polled handlers. Defeats the point of the helpers (and the
zero-runtime-deps posture).

### D5. Event factory: `make_event(request_type, ...)`

```python
def make_event(
    request_type: Literal["Create", "Update", "Delete"] = "Create",
    *,
    stack_id: str = "arn:aws:cloudformation:us-east-1:111111111111:stack/test-stack/abc",
    request_id: str = "00000000-0000-0000-0000-000000000000",
    logical_resource_id: str = "TestResource",
    physical_resource_id: str | None = None,    # required for Update/Delete
    resource_type: str = "Custom::Test",
    resource_properties: dict[str, Any] | None = None,
    old_resource_properties: dict[str, Any] | None = None,   # Update only
    response_url: str = "https://example.invalid/cfn-response",
    service_token: str = "arn:aws:lambda:us-east-1:111111111111:function:test",
) -> dict[str, Any]: ...
```

Rationale for sensible defaults:
- ARNs are syntactically valid (will parse) but use the reserved
  `111111111111` example account ID and `example.invalid` host so
  no production system is accidentally hit if a test misroutes.
- `physical_resource_id` defaults to `None` because Create events
  don't carry one; for Update/Delete the function raises
  `ValueError` if not supplied. (Better to fail loudly than to
  silently use a Create-shaped event for an Update test.)

**Rejected alternative**: separate factories per request type
(`make_create_event`, `make_update_event`, `make_delete_event`).
Three names where one suffices, and the validation logic for
"physical_resource_id required for Update/Delete" is the same in
all three.

**Update consideration**: actually, three named factories MAY
be clearer. Reconsider in implementation; either works. The pytest
fixtures (next decision) will be three named fixtures regardless.

### D6. pytest fixtures via `pytest11` entry point

```toml
[project.entry-points.pytest11]
cfn_handler = "cfn_handler.testing.fixtures"
```

The fixtures module exposes:

```python
@pytest.fixture
def cfn_create_event() -> dict[str, Any]: ...

@pytest.fixture
def cfn_update_event() -> dict[str, Any]: ...

@pytest.fixture
def cfn_delete_event() -> dict[str, Any]: ...

@pytest.fixture
def cfn_lambda_context() -> LambdaContext: ...
```

Each fixture returns a fresh dict/object on every call (no shared
state). Users can override fields per-test via standard pytest
patterns:

```python
def test_my_handler(cfn_create_event):
    cfn_create_event["ResourceProperties"] = {"Foo": "bar"}
    resource = CustomResource()
    @resource.create
    def on_create(event, ctx): return {"Endpoint": "x"}

    replay = resource.replay(cfn_create_event)
    assert_success(replay, data={"Endpoint": "x"})
```

**Rejected alternative**: requiring `pytest_plugins = ["cfn_handler.testing"]`
in users' `conftest.py`. The entry point is the modern, automatic way.

**Risk to flag**: pytest fixtures have global names. If a user already
has a `cfn_create_event` fixture for some reason, ours collides. We
prefix with `cfn_` to minimise collision; users who hit it can
override with their own (pytest's local fixtures win over plugin ones).

### D7. Assertion helpers

```python
def assert_success(
    replay: Replay,
    *,
    data: dict[str, Any] | None = None,
    physical_resource_id: str | None = None,
    no_echo: bool | None = None,
) -> None: ...

def assert_failed(
    replay: Replay,
    *,
    reason_contains: str | None = None,
    physical_resource_id: str | None = None,
) -> None: ...

def assert_deferred(
    replay: Replay,
    *,
    rule_arn_present: bool = True,
) -> None: ...
```

Each performs `AssertionError`-raising checks suitable for use inside
pytest tests. Optional kwargs are matched only when supplied (so
`assert_success(replay)` is "any success", and
`assert_success(replay, data={...})` is "success AND data exactly
matches").

**Rationale**: pytest's `assert` plus `replay.status == "SUCCESS"`
also works. The helpers exist for ergonomics: a single line that
captures intent, with informative `AssertionError` messages.

**Rejected alternative**: a hamcrest-style `is_success()` matcher.
Adds a dep, not idiomatic in pytest.

### D8. Documentation surface

The README gains a "Testing" section showing one minimal example.
A new top-level page (`docs/TESTING.md` or similar) is candidate
but not required for v1.3.0; the docstrings on `replay`,
`make_event`, and the assertion helpers should carry their weight.

A new `examples/testing/` directory is **not** part of this change
(would expand scope). Add later if user feedback warrants.

## Risks / Trade-offs

| Risk                                                                   | Mitigation                                                                                                                                            |
|------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| Internal seam complicates the dispatch code                            | Default the `transport` param everywhere; existing call sites stay unchanged. Production code paths see no change.                                    |
| `pytest11` entry point loads `cfn_handler.testing.fixtures` in any pytest run, even ones not using cfn-handler | Fixtures only consume memory if requested; the import itself is cheap (no sys.modules pollution beyond `cfn_handler.testing`).                       |
| Fixture name collision (`cfn_create_event` etc.) with users who happen to have such fixtures | Use `cfn_` prefix; document override pattern. Local fixtures win in pytest's resolution order.                                                       |
| Replay's behaviour drifts from production behaviour (false-positive tests) | Dogfood: rewrite the existing test suite (or a representative subset) on top of the new helpers. If a test that passes via replay would have failed in production, the seam is wrong. |
| Polling stub fails to faithfully reproduce real polling behaviour      | Cover both "stub records call" and "stub mutates event" in the spec scenarios. Run an end-to-end test (existing moto-based) alongside to verify parity. |
| `Replay.status="DEFERRED"` accidentally leaks into production code (somebody catches it as if real) | Document explicitly: DEFERRED is a sentinel for replay only; production status is always `"SUCCESS"` or `"FAILED"`. Lint rule (later, in `cfn-lint-cfn-handler`) could catch this. |

## Migration Plan

This is purely additive — no migration path for users. The change ships
as `1.3.0` (minor bump). Users who don't import `cfn_handler.testing`
see no difference.

For the project itself: the existing test suite stays as it is. Once the
helpers ship and prove themselves on a few new tests, a separate
follow-up PR can opportunistically rewrite older tests onto the
helpers. That's not part of this change.

## Open Questions

1. **Single `make_event(request_type=...)` vs three named factories
   (`make_create_event`, etc.)?** Both work. Decide during
   implementation based on which reads better in fixture code. (D5
   leans toward single factory, but happy to be overruled by the
   tests as they get written.)
2. **Should `assert_success(replay, data={...})` perform exact match
   or subset match?** Default exact (matches `dict == dict`); add a
   `data_subset=` kwarg if subset is needed. Decide based on
   first uses.
3. **Should `make_event` validate the `RequestType` it produces against
   a known set?** `Literal["Create", "Update", "Delete"]` already gives
   us static checks; runtime validation is belt-and-braces. Leaning yes
   for clear errors, no for simplicity. Decide during implementation.
4. **Should the testing module be importable when only stdlib is
   available (no boto3, no pytest)?** Yes — but only if the user
   sticks to factories and assertions. Importing the fixtures
   module without pytest installed should fail gracefully (lazy import).
