# Tasks: Add testing helpers

> Apply order: tasks within a phase MAY be parallelised when no
> dependency exists. Phases are sequential. Each task ends with a
> verification command in backticks.
>
> TDD discipline: in phases 2–6, write tests **before** implementation.
> A green run after writing the test means the test is wrong (it should
> fail until implementation lands).

## 1. Scaffolding

- [x] 1.1 Create directory `src/cfn_handler/testing/` with `__init__.py`,
      `_internal/__init__.py`, and a `py.typed` marker copied from
      the package root. Verify: `ls src/cfn_handler/testing/`
- [x] 1.2 Add an empty `cfn_handler/testing/fixtures.py` placeholder
      so the `pytest11` entry-point lookup later doesn't fail at
      collection time. Verify: `python -c "import cfn_handler.testing.fixtures"`
- [x] 1.3 Update `pyproject.toml`:
      - Add `[project.entry-points.pytest11]` table with
        `cfn_handler = "cfn_handler.testing.fixtures"`.
      - Verify the entry point appears in the built wheel:
        `uv build && unzip -p dist/*.whl '*entry_points.txt' | grep pytest11`
- [x] 1.4 Update `[tool.hatch.build.targets.wheel].packages` and
      `[tool.hatch.build.targets.sdist].include` to include the new
      `src/cfn_handler/testing` subtree (verify: a built wheel contains
      `cfn_handler/testing/__init__.py`).
- [x] 1.5 Run baseline checks before any logic lands: `just lint
      typecheck test-cov`. Repo MUST be green.

## 2. Internal seam — Transport callable

- [x] 2.1 Write a failing test that monkeypatches an in-memory
      transport into `CustomResource` and asserts the test transport is
      called instead of `_internal.response.send_response`. Place under
      `tests/unit/test_transport_seam.py`. Verify: `uv run pytest
      tests/unit/test_transport_seam.py -x` fails.
- [x] 2.2 Define the `Transport` callable type in
      `src/cfn_handler/_internal/response.py` (or a new file
      `src/cfn_handler/_internal/transport.py` if it grows beyond a
      single alias). Type:
      `Transport = Callable[[str, dict[str, Any]], None]`.
- [x] 2.3 Add `transport: Transport | None = None` parameter to
      `CustomResource.__init__`. Default to a thin wrapper that calls
      `send_response` (existing behaviour preserved). Replace direct
      `send_response` call sites in `resource.py` with calls through
      `self._transport`. Verify: 2.1 test now passes; full suite still
      green: `uv run pytest`.
- [x] 2.4 Type-check passes with the new generic: `uv run mypy
      src/cfn_handler && uv run pyright src/cfn_handler`.

## 3. Internal seam — Poller stubs

- [x] 3.1 Write a failing test that asserts: when a poll handler is
      registered AND a stub poller is injected, the lifecycle dispatch
      calls the stub, never imports boto3, and mutates the event with
      polling marker keys. Place under
      `tests/unit/test_poller_seam.py`.
- [x] 3.2 Define `PollerProvision` and `PollerTeardown` callable types
      in `src/cfn_handler/_internal/poller.py`. Add equivalent
      injection seam to `CustomResource.__init__`
      (`provision_poller`, `teardown_poller` defaulting to the existing
      module-level functions).
- [x] 3.3 Wire `setup_polling` / `teardown_polling` calls in
      `resource.py` to go through the seam. Verify 3.1 test passes;
      existing polling test suite still green: `uv run pytest
      tests/`.

## 4. Public testing surface — `Replay` + `replay()`

- [x] 4.1 Write spec scenarios as failing tests in
      `tests/unit/testing/test_replay.py` covering:
      - Successful create handler → `Replay(status="SUCCESS", ...)`
      - Handler raises → `Replay(status="FAILED", reason=...)`
      - No HTTP I/O performed (assert via instrumented transport)
      - boto3 not imported (assert `"boto3" not in sys.modules` after
        a replay that does NOT use polling, in a subprocess to avoid
        prior pollution)
      - `Replay` is frozen (FrozenInstanceError on mutation)
- [x] 4.2 Implement `Replay` dataclass in
      `src/cfn_handler/testing/_internal/replay_result.py` per the
      design (frozen, slots, all fields). Re-export from
      `cfn_handler.testing`.
- [x] 4.3 Implement `CustomResource.replay(event, context=None)`:
      builds a capturing transport + stub pollers, swaps them in via
      `dataclasses.replace`-style or constructor-args (decide during
      implementation), runs the dispatch, captures the rendered
      payload, returns the `Replay`. Restore production transport on
      both normal and exceptional return.
- [x] 4.4 Verify: `uv run pytest tests/unit/testing/`. Verify
      coverage of `replay()` is at 100% line+branch (replay is
      a small surface; nothing should be uncovered).

## 5. Public testing surface — Polling-aware replay

- [x] 5.1 Write failing test: `replay()` of a Create event with both
      `@create` and `@poll_create` registered returns
      `Replay(status="DEFERRED")` and mutates the event to include
      `CfnHandlerPoll=True`, `CfnHandlerRule=...`,
      `CfnHandlerPermission=...`.
- [x] 5.2 Write failing test: a second `replay()` call with the
      mutated event resumes through the poll handler. If the poll
      handler returns data, the result is
      `Replay(status="SUCCESS", data=...)`.
- [x] 5.3 Implement the stub `provision_poller`: mutates the event
      to add the same marker keys real polling adds, records the call
      args (the existing real `setup_polling` mutates and returns
      `None`; the stub follows the same shape). Implement stub
      `teardown_poller` as a no-op recorder.
- [x] 5.4 Wire stubs into `replay()`. Verify: 5.1 + 5.2 pass.
- [x] 5.5 Add a parity test: same handler, run once via
      `CustomResource.__call__` against a moto-mocked AWS environment
      (existing pattern in `tests/integration/`), once via `replay()`.
      Assert that the rendered payload is byte-equal in both cases
      (excluding ARNs/IDs that vary per run).

## 6. Public testing surface — Factories + assertions

- [x] 6.1 Write failing tests for `make_event`:
      - Default Create event has expected shape
      - Update/Delete missing physical_resource_id raises `ValueError`
      - Field overrides applied
      - Defaults use safe placeholders (`example.invalid`,
        `111111111111`)
- [x] 6.2 Implement `make_event` in `src/cfn_handler/testing/
      _internal/event_factory.py`. Re-export from
      `cfn_handler.testing`.
- [x] 6.3 Write failing tests for `make_context`:
      - Returns object satisfying `LambdaContext` protocol
      - `remaining_time_ms` override honoured
- [x] 6.4 Implement `make_context`.
- [x] 6.5 Write failing tests for `assert_success`, `assert_failed`,
      `assert_deferred` covering both pass and fail paths and the
      message contents on failure.
- [x] 6.6 Implement assertion helpers in
      `src/cfn_handler/testing/_internal/assertions.py`. Re-export.

## 7. pytest fixtures

- [x] 7.1 Write a failing test in a *fresh* pytest project layout
      (under `tests/integration/test_fixture_discovery/`) — a single
      `conftest.py`-free directory with a test that depends on
      `cfn_create_event`. Run via `uv run pytest --rootdir=...`
      pointed at the temp directory. Verify the fixture is found.
- [x] 7.2 Implement the fixtures in
      `src/cfn_handler/testing/fixtures.py`:
      `cfn_create_event`, `cfn_update_event`, `cfn_delete_event`,
      `cfn_lambda_context`. Each is a pytest fixture returning
      a fresh value built via `make_event` / `make_context`.
- [x] 7.3 Verify each fixture invocation is independent (no shared
      state across tests).
- [x] 7.4 Confirm fixture loading does NOT add overhead in pytest
      runs that don't use them: `uv run pytest --collect-only -q | wc
      -l` baseline matches pre-change collection count.

## 8. Public surface wiring

- [x] 8.1 Update `src/cfn_handler/testing/__init__.py` to export
      exactly the public names: `Replay`, `make_event`,
      `make_context`, `assert_success`, `assert_failed`,
      `assert_deferred`. Define `__all__` accordingly.
- [x] 8.2 Verify NOTHING from `_internal/` is exposed via
      `cfn_handler.testing`: `python -c "import cfn_handler.testing as
      t; print(sorted(n for n in dir(t) if not n.startswith('_')))"`
      output matches the `__all__`.
- [x] 8.3 Confirm the package root `cfn_handler.__all__` is
      **unchanged** (no testing names leak into the production root).

## 9. Soft-deprecate `test_mode` / `last_response`

- [x] 9.1 Write a failing test asserting that
      `CustomResource(test_mode=True)` emits a `DeprecationWarning`
      whose message references `replay()` and points at
      `cfn_handler.testing`. Place under
      `tests/unit/test_test_mode_deprecation.py`. Verify: test fails.
- [x] 9.2 Add `warnings.warn(..., DeprecationWarning, stacklevel=2)`
      in `CustomResource.__init__` when `test_mode=True`. Verify 9.1
      passes.
- [x] 9.3 Update the docstring on `test_mode` and `last_response`
      to mark them as deprecated and reference `replay()`.
- [x] 9.4 Update `pytest.ini_options.filterwarnings` to NOT promote
      this specific deprecation to an error in our own test suite
      until the migration in §10 is complete (then revert in §10.5).

## 10. Migrate existing test suite to `replay()`

- [x] 10.1 Sweep: enumerate every test file referencing `test_mode=`
      or `last_response`. Expected sites (from grep): `tests/unit/
      test_resource.py`, `test_backstops.py`, `test_polling_dispatch.py`,
      `test_state_machine.py`. Verify count: `grep -rn 'test_mode\|
      last_response' tests/ | wc -l` matches expectation before any edits.
- [x] 10.2 Migrate `tests/unit/test_resource.py` from `test_mode=True`
      + `last_response` reads to `replay()` + `Replay` field reads.
      Use the new assertion helpers (`assert_success`,
      `assert_failed`) where they match the existing assertion shape.
      Verify: file's tests still pass after migration.
- [x] 10.3 Migrate `tests/unit/test_backstops.py`. Verify: tests pass.
- [x] 10.4 Migrate `tests/unit/test_polling_dispatch.py`. The polling
      sentinel test (`test_create_with_poll_handler_in_test_mode_records_sentinel`)
      becomes a `Replay(status="DEFERRED")` assertion via
      `assert_deferred`. Verify: tests pass.
- [x] 10.5 Migrate `tests/unit/test_state_machine.py`. Verify: tests
      pass. After all migrations: `grep -rn 'test_mode\|last_response'
      tests/` should return ZERO matches.
- [x] 10.6 Revert the `pytest.ini_options.filterwarnings` exception
      from 9.4. Tests now must NOT emit the deprecation warning;
      if any do, the suite fails (forcing the migration to be
      complete).

## 11. Documentation

- [x] 11.1 Add a "Testing" section to `README.md` between "Examples"
      and "Project status". One minimal example showing
      `make_event` + `replay` + `assert_success`.
- [x] 11.2 Docstrings on every public name in `cfn_handler.testing`
      following Google-style convention (matches existing project
      docstrings). Verify: `uv run ruff check src/cfn_handler/testing`
      catches any missing docstrings (the `D` ruleset is on for
      `src/`).
- [x] 11.3 Add an entry to `docs/ROADMAP.md` moving testing helpers
      from "Active priorities" to a "Shipped in 1.3.0" reference (or
      delete it entirely; the spec is the durable record).
- [x] 11.4 ~~Add a `CHANGELOG.md` deprecation entry~~ — N/A.
      `CHANGELOG.md` is auto-managed by release-please from
      Conventional Commits. The deprecation context goes in the
      squash-merge commit body (see §12.4).

## 12. Coverage + final checks

- [x] 12.1 Run `just ci-check` (lint + typecheck + test-cov). Coverage
      MUST be ≥95% line+branch including the new module. Failures here
      block release. **Result: 98% coverage, 152 tests passing, lint
      and types clean.** Note: switched `test-cov` to use `coverage
      run -m pytest` instead of `pytest --cov` because the new
      `pytest11` entry point causes `cfn_handler` to be imported
      during pytest plugin collection (before `--cov` instrumentation
      attaches), making module-level lines look unhit. Documented in
      the recipe comment.
- [ ] 12.2 Run `just gha-pre-release` to replay every CI gating
      workflow locally. All green required before merge. **Defer to
      pre-merge step.**
- [x] 12.3 Verify the built wheel includes `cfn_handler/testing/`:
      `uv build && unzip -l dist/*.whl | grep testing`. Verified —
      9 files including `_internal/` modules and `py.typed`.
- [ ] 12.4 Verify the conventional-commit message for the squash-merge
      starts with `feat(testing):` so release-please bumps minor
      (target: `1.3.0`). **Squash-merge commit message guidance:**
      ```
      feat(testing): add cfn_handler.testing module with replay() helpers

      Adds the new `cfn_handler.testing` public surface:
      - `CustomResource.replay(event, context=None)` — in-process dispatch
        returning a structured `Replay` (no HTTP, no boto3).
      - `Replay` frozen dataclass.
      - `make_event` / `make_context` factories with safe defaults.
      - `assert_success` / `assert_failed` / `assert_deferred` helpers.
      - pytest fixtures (`cfn_create_event`, `cfn_update_event`,
        `cfn_delete_event`, `cfn_lambda_context`) auto-discovered via
        the `pytest11` entry point.

      DEPRECATED: `CustomResource(test_mode=True)` and `last_response`
      now emit a DeprecationWarning. They continue to work in v1.x;
      removal scheduled for v2.0.
      ```
      **Defer to merge step.**

## 13. Validation

- [x] 13.1 Validate the change strictly: `openspec validate
      add-testing-helpers --strict`. All artifacts must pass.
      **Result: "Change 'add-testing-helpers' is valid".**
- [x] 13.2 Manual smoke test: in a fresh venv outside the repo, `uv
      add cfn_handler` from the local wheel and verify
      `import cfn_handler.testing` works and `make_event()` produces
      a Create event. **Result: smoke test passed —
      `replay(make_event(), make_context())` returns
      `Replay(status="SUCCESS", data={"Endpoint": "https://smoke.example"})`
      and `assert_success` passes.**
