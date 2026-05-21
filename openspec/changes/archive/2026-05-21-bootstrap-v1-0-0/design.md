# Design: Bootstrap cfn-handler v1.0.0

## Context

CloudFormation Custom Resources are AWS Lambda functions invoked by CloudFormation during stack lifecycle events. The Lambda receives a JSON event describing the request type and resource properties, performs work, and reports the outcome back to CloudFormation by HTTP-PUTting a JSON payload to a presigned `ResponseURL`. Failure to respond — or a malformed response — causes CloudFormation to hang for up to an hour before timing out the stack.

The reference helper library (`crhelper`) was sound in concept but accumulated unfixed bugs: PRs sat for years, the polling logic had a known retry-loop defect (#20/#34/#39/#51), the `init_failure` path leaked process IDs (#7/#67), AWS Lambda's `LambdaContext` type was untyped (#76), no test-mode existed for unit testing handlers (#52/#54), and packaging was stuck on `setup.py`.

A fork at `igorlg/custom-resource-helper` modernized the build (uv + pyproject + GitHub Actions matrix), ported the test suite to plain pytest, and merged the proven community fixes. That work demonstrated all 41 existing tests can be carried forward and the public API remains compact (one class, three decorators, three poll decorators, one exceptions module). The fork hit a ceiling: upstream is unlikely to merge breaking improvements, and continuing to call the project `crhelper` ties our identity to the dormant upstream.

This change establishes a clean baseline: a new repo, new package name (`cfn-handler`), new git history, and modern engineering practices applied uniformly. The goal is a v1.0.0 that we can defend as well-engineered to any code reviewer five years from now.

## Goals / Non-Goals

**Goals:**
- Ship a Python ≥3.10 library with zero runtime dependencies, distributed on PyPI as `cfn-handler`.
- Public API is `CustomResource` plus an exception hierarchy. Users `from cfn_handler import CustomResource`.
- Every behaviour proven in the upstream fork (14 fixed issues) is preserved and covered by tests.
- Test suite uses pytest + hypothesis with ≥95% line + branch coverage enforced in CI.
- All tooling configuration consolidated in `pyproject.toml` (single source of truth).
- CI runs on every supported Python version (3.10–3.14) on linux/amd64 and linux/arm64.
- Releases are fully automated via release-please + PyPI Trusted Publishing (no API tokens).
- Repository hygiene: SHA-pinned third-party actions, least-privilege workflow permissions, grouped Dependabot, CodeQL SAST, dependency review on PRs.
- Reproducible developer environment via Nix flake (flake-parts) for contributors who use Nix.

**Non-Goals:**
- TypeScript / JavaScript / Rust ports.
- Documentation site (mkdocs / readthedocs). Docstrings + README only.
- Pre-commit hooks (CI is the source of truth).
- Lambda Layer publishing automation.
- SLSA L3 provenance, OSSF Scorecard, ClusterFuzzLite, fuzzing.
- Backwards compatibility shim for `crhelper` users (different name = different identity).
- Multi-handler-per-resource support (covered by `aws-cloudformation/custom-resource-helper#13`; deferred).
- Persistent poller state across Lambda invocations beyond CloudWatch Events (#27; deferred).

## Decisions

### D1 — Package name: `cfn-handler` (import: `cfn_handler`)

Considered: `cfn-resource-helper` (continuity with fork), `cfn-custom`, `cfn-cr`, `cfnforge`, `cradle`. Selected `cfn-handler` because:
- It states the function: this is the *handler* for a CFN custom resource Lambda.
- `cfn-` prefix aligns with AWS's own ecosystem conventions (`cfn-lint`, `cfn-flip`).
- `from cfn_handler import CustomResource` reads cleanly without redundant prefixes.
- Available on PyPI, GitHub, and (verified) common npm-package-name spaces should we ever go polyglot.
Rejected alternatives:
- `cforge`/`cradle`: taken on PyPI by unrelated active projects.
- `cfn-cr`: too cryptic; "CR" alone is unclear.
- Keeping `cfn-resource-helper`: "helper" weakens identity; we want a focused name.

### D2 — Build backend: `hatchling`

Considered: `setuptools`, `poetry-core`, `flit-core`, `hatchling`. Selected `hatchling`:
- PEP 621 native (no `[tool.poetry]` parallel metadata block).
- No `setup.py` generation; lean wheel/sdist output.
- Active upstream development; default for `uv init --lib` and many new libraries.
- Trivial config; no plugins required for our use case.
Rejected: `setuptools` works, but config is verbose and `pyproject.toml` + `MANIFEST.in` split is awkward; `poetry-core` would force `poetry`-isms (groups, lock format) on top of `uv`; `flit-core` is fine for trivial libs but lacks the build-time hooks we may want later.

### D3 — Source layout: `src/cfn_handler/...`

The `src/` layout prevents accidental imports of unbuilt source code during testing (a common cause of "passes locally, fails in CI" issues). Modern PyPA guidance defaults to it; powertools-lambda-python is a notable holdout but its rationale (tooling lag) no longer applies.

### D4 — Privacy via folder placement, not name prefix

`_internal/` subpackage holds all private modules. Public modules at the package root (`resource.py`, `exceptions.py`) are re-exported via `__init__.py`. We avoid `_module.py` prefix because it produces ugly imports in the type-stub-less world we live in (with `py.typed`, IDEs surface every prefixed module by name). Folder grouping reads cleaner and matches the powertools-lambda-python convention that survives at scale.

### D5 — Public API surface: minimal, explicit `__all__`

`from cfn_handler import *` exposes exactly:
- `CustomResource` — the class users instantiate.
- `CfnHandlerError`, `ResponseError` — the exception hierarchy.
- `__version__` — sourced via `importlib.metadata.version(__package__)` so it stays in lockstep with the wheel metadata; release-please bumps `pyproject.toml` and the value follows automatically.

Everything else (`cfn_handler._internal.*`) is implementation detail and may change between minor versions. This is documented in CONTRIBUTING.md.

### D6 — Test framework: pytest + hypothesis, no unittest

Plain functions named `test_*`, fixtures via `conftest.py`. Hypothesis is added specifically to property-test the polling state machine (CREATE/UPDATE/DELETE × poll/no-poll × time-budget × handler-outcome — easily a thousand discrete combinations that hypothesis enumerates in seconds).

JSON event fixtures live in `tests/events/*.json` (powertools pattern) loaded by named fixtures. This makes them reusable across test tiers and eliminates the noise of multi-line dict literals in test files.

Coverage: 95% line + branch enforced in `pyproject.toml`. Chosen at 95 (not 90 or 100) because the state machine logic justifies branch coverage, and the few practically-untestable branches (e.g. catastrophic `urllib` errors at module import) leave roughly 5% room without inviting `# pragma: no cover` abuse.

### D7 — Two type checkers: mypy strict + pyright strict

Mypy and pyright catch different classes of bug — mypy's plugin ecosystem and broader adoption make it the "ground truth" for the open-source ecosystem; pyright's stricter inference catches subtle inference issues mypy waves through (and is what most LSP-driven IDEs use, so it matches user experience). Running both costs ~10 seconds in CI for a library of this size. Worth it.

We do *not* adopt Astral's `ty` even though powertools-lambda-python does — `ty` is alpha and we'd be the canary for any false positives that block our release.

### D8 — Logger calls use lazy `%s` formatting

`logger.debug("Sending response to %s", url)` rather than `logger.debug(f"Sending response to {url}")`. Standard library lazy formatting preserves level deferral (the format string is only resolved if the level is enabled). Ruff's `UP031` only fires on `%` operator usage, not on lazy logger calls — so this stays compatible with `select = ["UP"]`.

### D9 — CI matrix and pinning

Test matrix: `python-version: [3.10, 3.11, 3.12, 3.13, 3.14]` × `runner: [ubuntu-latest, ubuntu-24.04-arm]` = 10 jobs, plus 1 lint job (ruff + mypy + pyright). All third-party actions SHA-pinned with `# vX.Y.Z` comments. A separate `secure-workflows.yml` runs `zgosalvez/github-actions-ensure-sha-pinned-actions` on PRs touching `.github/workflows/**` and fails the PR if a tag-pinned action sneaks in.

`actions/setup-uv@<sha>` (currently `astral-sh/setup-uv` v8) is the canonical setup; uv handles caching internally so we don't need `actions/cache@`. PRs use `concurrency: cancel-in-progress: true`; `release.yml` does not (releases shouldn't cancel mid-publish).

### D10 — Release pipeline: release-please + PyPI Trusted Publishing

Conventional Commits (`feat:` → minor, `fix:` → patch, `feat!:`/`BREAKING CHANGE:` → major). release-please opens chore PRs from accumulated commits; merging the chore PR triggers tag creation, GitHub Release creation, artifact upload, and PyPI publish via OIDC Trusted Publisher (no API token managed). The PyPI project must be created and Trusted Publisher pre-configured before the first release can succeed (manual one-time setup).

### D11 — Nix flake: dendritic / flake-parts style

The flake uses `flake-parts` and `import-tree` so future modules can be auto-imported by directory placement (Igor's "import == enable" convention). For a single-file library the flake is small, but the structure is correct from day one to match Igor's other Nix projects. Provides `devShells.default` with: Python 3.12 (the CI baseline for type-checking), uv, just, ruff, gh, act, pre-commit-hooks bins as needed.

### D12 — Examples directory: multiple SAM-deployable scenarios

`examples/` contains:
- `basic/` — minimal Create/Update/Delete handler (no polling).
- `polled/` — long-running operation with polling (e.g. fake "wait for resource ready").
- `with-physical-id/` — explicit `physical_resource_id` override demonstrating UPDATE-as-replacement.
- `failing/` — handler that raises, demonstrating FAILED response semantics.
Each example is a deployable SAM project with `template.yaml` + `src/handler.py` + `README.md`. Examples are not auto-built by docs (no docs site), but each example is `cfn-lint`'d in CI to keep templates valid.

### D13 — Repository identity: brand new, single initial commit

We squash to a single `feat: initial release (inspired by aws-cloudformation/custom-resource-helper)` commit on the new repo. Apache 2.0 §4 attribution is preserved in the LICENSE file via dual copyright header. The git history of the fork is not preserved — anyone who needs to see the modernization arc can browse the archived `igorlg/custom-resource-helper` repo.

## Risks / Trade-offs

- **[Risk] Discovery: users searching `crhelper` won't find us.** → Mitigation: README opens with "drop-in spiritual successor to crhelper"; `keywords` in pyproject include both names; archived fork's README points here.
- **[Risk] Two type-checkers double the maintenance when one disagrees with the other.** → Mitigation: in the rare cases we cannot satisfy both, prefer mypy and add `# pyright: ignore[<rule>]` with a comment; document the policy in CONTRIBUTING.md. Current code passes both today.
- **[Risk] Hypothesis state-machine tests can be flaky if the modeled state space is wrong.** → Mitigation: keep the state machine model small (handler-set × request-type × time-budget × handler-outcome), use `@settings(deadline=None, max_examples=200)` to keep CI fast and deterministic, and `pytest.skip` the hypothesis tests under coverage when they slow runs measurably.
- **[Risk] PyPI Trusted Publisher needs a one-time manual setup; the first release will fail without it.** → Mitigation: documented step in CONTRIBUTING.md and in the release-PR description template. release-please retries are cheap; we can re-run the failed publish job after configuring the publisher.
- **[Risk] Zero runtime deps means polling code must use `boto3` only when present (Lambda runtimes ship it but local tests don't).** → Mitigation: `import boto3` lazily in `_internal/poller.py`; raise a `CfnHandlerError` subclass with a helpful message if absent. Tests use `moto` (a dev dep) to mock CloudWatch Events.
- **[Risk] Apache 2.0 attribution mistakes.** → Mitigation: dual-copyright header in LICENSE, NOTICE file referencing upstream, README acknowledgement. Reviewable by a non-lawyer in 5 minutes.
- **[Risk] Squashing history loses the per-PR review trail of the fork's modernization.** → Mitigation: archived fork remains read-only on GitHub forever; commit messages on the squash reference the fork's PRs by number for traceability.
- **[Trade-off] No docs site means API discovery relies on docstrings + IDE tooling.** → Acceptable given the small public surface (one class). Add mkdocs in a later change if user feedback demands it.
- **[Trade-off] No pre-commit hooks shipped.** → Contributors who want them locally can install the same checks via `just lint`; we don't ship a `.pre-commit-config.yaml` to maintain.

## Migration Plan

There is no in-place migration; this is a green-field bootstrap. The transition for users of the existing fork is:

1. Configure PyPI Trusted Publisher binding for `cfn-handler` (manual, one-time, by repo owner).
2. Create GitHub repo `igorlg/cfn-handler` (empty, default branch `main`).
3. Apply the bootstrap commit produced by this change.
4. CI runs and stays green; first release-please PR opens automatically.
5. Merge the release PR → first PyPI publication of `cfn-handler` 1.0.0.
6. Archive `igorlg/custom-resource-helper` and update its README to point here.

Rollback: if a critical defect is found post-1.0.0, yank the version on PyPI and ship 1.0.1 with a fix. There is no rollback to the fork — once published, the new project is the canonical home.

## Open Questions

None blocking. Items deferred to future changes:
- Lambda Layer publishing pipeline (separate change).
- mkdocs documentation site (separate change, only if demand emerges).
- `SPEC.md` for polyglot conformance (separate change, only if a TS / Rust port is started).
- Hypothesis test settings tuning under heavy CI load (handle as it arises).
