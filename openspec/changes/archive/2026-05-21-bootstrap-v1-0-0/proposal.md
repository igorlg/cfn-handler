# Proposal: Bootstrap cfn-handler v1.0.0

## Why

CloudFormation Custom Resources are a routine part of AWS deployments, yet the official handler library (`aws-cloudformation/custom-resource-helper`, aka `crhelper`) has been effectively unmaintained for years (last release 2020), accumulating fixed-but-unmerged community PRs and lacking modern Python tooling. A fork at `igorlg/custom-resource-helper` already addressed 14 upstream issues and modernized the build, but staying tethered to the upstream name and history limits how far we can take it.

This change starts a new project — `cfn-handler` — designed from the ground up as a modern, well-engineered Python library inspired by but no longer derived from `crhelper`. We get to choose the public API shape, internal architecture, tooling, CI pipeline, and release cadence without inheriting any legacy decisions. The goal is a library users can depend on for the next decade.

## What Changes

### Library (user-facing)
- **NEW** `cfn-handler` package on PyPI, `from cfn_handler import CustomResource`.
- **NEW** Public API surface: `CustomResource` class with `@create`, `@update`, `@delete`, `@poll_create`, `@poll_update`, `@poll_delete` decorators; explicit exception hierarchy.
- **NEW** Polling state machine for long-running custom resources (re-invoke via CloudWatch Events).
- **NEW** Type-safe end to end: `py.typed` marker, full inline annotations, mypy strict + pyright strict.
- **NEW** Carries forward all 14 fixes proven in the fork: upstream issues #7, #19, #20, #34, #36, #39, #51, #52, #54, #62, #66, #67, #76, #78.

### Project (developer-facing)
- **NEW** `src/` layout (`src/cfn_handler/...`), folder-based privacy via `_internal/`.
- **NEW** Build backend: hatchling (PEP 621 native, no `setup.py` generation).
- **NEW** Dual type-checker CI: mypy (strict) + pyright (strict).
- **NEW** Test suite: pytest + hypothesis (state-machine property tests for the lifecycle), ≥95% line + branch coverage gate.
- **NEW** All tooling configuration consolidated in `pyproject.toml` (no `ruff.toml`, `mypy.ini`, `tox.ini`, `.flake8`).
- **NEW** Five GH Actions workflows: `ci.yml` (matrix test + lint), `release.yml` (release-please + PyPI Trusted Publishing), `codeql.yml`, `dependency-review.yml`, `secure-workflows.yml` (SHA-pin enforcement).
- **NEW** Grouped Dependabot updates.
- **NEW** Reproducible dev shell via Nix flake (flake-parts) for contributors who use Nix.
- **NEW** Examples directory with multiple SAM-deployable scenarios.
- **NEW** Repo metadata: README, LICENSE (Apache-2.0 with dual copyright preserving upstream Amazon attribution), CHANGELOG.md (release-please managed), CONTRIBUTING.md, SECURITY.md, CODE_OF_CONDUCT.md.
- **NEW** `justfile` task runner with recipes for lint, type-check, test, build, lock, clean, and `act`-driven local CI matrix.

### Non-goals
- **No** TypeScript, Rust, or other language ports in this release. A `SPEC.md` describing the contract may be written later for polyglot implementations to conform to, but not now.
- **No** documentation site (mkdocs) in this release. README + comprehensive docstrings only.
- **No** pre-commit hooks shipped. CI is the source of truth.
- **No** Lambda Layer publishing automation in v1.0.0 (deferred to a future change).
- **No** SLSA L3 provenance, OSSF Scorecard, ClusterFuzzLite, or other supply-chain extras beyond the basics listed above.

## Capabilities

### New Capabilities
- `lifecycle-handler`: The `CustomResource` entry point — registering CREATE/UPDATE/DELETE handlers, dispatching CloudFormation events, and returning structured responses.
- `polling`: Polling state machine for long-running operations — handler returns `IN_PROGRESS`, lambda re-invokes via CloudWatch Events until completion or timeout.
- `error-handling`: Exception hierarchy and failure semantics — what gets reported as `FAILED` to CloudFormation vs raised vs logged.

### Modified Capabilities
None — this is a green-field project. No existing specs in `openspec/specs/` to modify.

## Impact

- **Code**: Brand new repository at `igorlg/cfn-handler`; no migration path from `crhelper` users (intentional — different package name signals different identity).
- **APIs**: Public API is `cfn_handler.CustomResource` and the exceptions in `cfn_handler.exceptions`. Everything else (`cfn_handler._internal.*`) is private and may change without notice.
- **Dependencies**: Zero runtime dependencies (Python stdlib only). Dev dependencies pinned via `uv.lock`.
- **Systems**: PyPI project `cfn-handler` (created fresh; old `cfn-resource-helper` slot was reserved but never published, so no yank needed). GitHub repo `igorlg/cfn-handler`. PyPI Trusted Publisher binding to `release.yml`.
- **Existing fork**: `igorlg/custom-resource-helper` will be archived and its README updated to point at this project.
