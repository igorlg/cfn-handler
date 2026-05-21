# Spec: ci-infrastructure

## ADDED Requirements

### Requirement: All third-party GitHub Actions are pinned to commit SHAs

Every `uses:` reference in any workflow under `.github/workflows/` SHALL pin the action to a 40-character commit SHA, with a trailing comment recording the human-readable version (`# vX.Y.Z`). Annotated-tag SHAs are explicitly NOT permitted: GitHub's Docker actions resolve container images by commit SHA, and an annotated-tag SHA leads to a `manifest unknown` error at runtime.

#### Scenario: A workflow uses a tag-pinned action
- **WHEN** a contributor opens a PR introducing `uses: actions/checkout@v6`
- **THEN** the `secure-workflows.yml` workflow fails the PR with a non-SHA-pin error

#### Scenario: A workflow uses an annotated-tag SHA
- **WHEN** a contributor pins `pypa/gh-action-pypi-publish` to its tag-object SHA (the SHA returned by `gh api .../git/ref/tags/<tag>`) rather than its commit SHA
- **THEN** the workflow appears valid by visual inspection but fails at runtime with `docker: Error response from daemon: manifest unknown` when the Docker action attempts to pull its image

### Requirement: SHA-pin enforcement runs on every PR that touches workflows

A dedicated workflow (`secure-workflows.yml`) SHALL execute on pull requests that modify any file under `.github/workflows/**` and SHALL fail the PR if any action is not commit-SHA-pinned. The enforcement workflow MUST itself be SHA-pinned.

#### Scenario: A PR modifies a workflow with a tag-pin
- **WHEN** a PR adds or modifies `.github/workflows/<name>.yml` introducing a tag-pinned action
- **THEN** `secure-workflows.yml` runs and reports a failed status check on the PR

#### Scenario: A PR does not touch workflows
- **WHEN** a PR only modifies `src/`, `tests/`, or `docs/`
- **THEN** `secure-workflows.yml` does not trigger (saving CI minutes); branch protection does not require the check on such PRs

### Requirement: Workflow concurrency cancels superseded PR runs but never main runs

For workflows that gate PRs (e.g. `ci.yml`), the concurrency configuration SHALL cancel an in-progress run when a new push to the same PR ref arrives, AND SHALL NOT cancel runs on `main`. This is captured by `concurrency.cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.

#### Scenario: New push to an open PR
- **WHEN** a contributor force-pushes to a PR while the previous CI run is still executing
- **THEN** the previous run is cancelled and a new run starts from the latest commit

#### Scenario: Push to main while an earlier main run is executing
- **WHEN** a commit lands on `main` (e.g. via squash-merge) while an earlier `main` CI run is still executing
- **THEN** both runs complete; the earlier run is not cancelled

### Requirement: Per-job least-privilege permissions

Every workflow file SHALL declare a top-level `permissions: contents: read` (or stricter) and SHALL escalate permissions only on jobs that genuinely need them. Sensitive permissions — `id-token: write`, `contents: write`, `pull-requests: write` — MUST appear at the job level, never at the workflow level.

#### Scenario: A job needs to publish to PyPI via OIDC
- **WHEN** the `publish-pypi` job in `release.yml` runs
- **THEN** it has `id-token: write` declared at the job level; other jobs in the same workflow do NOT have that permission

#### Scenario: A job needs to create a tag and a GitHub Release
- **WHEN** the `release-please` job in `release.yml` runs
- **THEN** it has `contents: write` and `pull-requests: write` declared at the job level; other workflow jobs default to `contents: read`

### Requirement: Release pipeline driven by Conventional Commits and Trusted Publishing

Releases SHALL be driven entirely by Conventional Commits parsed by `release-please-action`. Merging the auto-generated release PR with the title `chore(main): release X.Y.Z` SHALL trigger a chain of jobs in `release.yml` that: tag `vX.Y.Z`; build wheel and sdist; upload artifacts to a GitHub Release; and publish to PyPI via OIDC Trusted Publishing in the `pypi` environment. The Trusted Publisher binding SHALL be parameterised by repository, workflow filename (`release.yml`), and environment name (`pypi`); no PyPI API token is held anywhere.

#### Scenario: A `feat:` commit lands on main
- **WHEN** a contributor merges a PR with title `feat: <description>` to `main`
- **THEN** `release-please-action` opens (or updates) a release PR proposing a minor version bump

#### Scenario: The release PR is merged
- **WHEN** the release PR is squash-merged
- **THEN** `release.yml` runs `release-please-action`, sees `release_created=true`, builds artifacts, uploads to GitHub Release, and the `publish-pypi` job authenticates via OIDC and uploads the artifacts to PyPI

#### Scenario: PyPI Trusted Publisher is misconfigured
- **WHEN** the publisher binding does not match (wrong workflow filename, wrong environment, wrong repo)
- **THEN** `pypa/gh-action-pypi-publish` fails the OIDC exchange and the publish step errors with a 403 from PyPI; the wheel/sdist artifacts on the GitHub Release are unaffected

### Requirement: Lockfile drift policy: `uv sync --frozen` in CI; manual `uv lock` after dependency edits

CI SHALL install dependencies via `uv sync --frozen --only-group <group>` rather than `--locked`. This is required because `release-please-action` bumps the local project's `version` in `pyproject.toml` but cannot also run `uv lock` to refresh the corresponding entry in `uv.lock`; under `--locked`, that drift breaks every CI run on `main` immediately after a release-please merge. `--frozen` still installs exactly the dependency versions recorded in `uv.lock`; only the local project's own version is read from the current `pyproject.toml`. Contributors SHALL run `uv lock` manually after editing `pyproject.toml` dependencies and commit the resulting `uv.lock` in the same PR.

#### Scenario: Post-release CI on main
- **WHEN** the release PR is merged, bumping `pyproject.toml` from `0.0.0` to `1.0.0` without an accompanying `uv.lock` update
- **THEN** the next `ci.yml` run on `main` succeeds, because `--frozen` does not check pyproject/lockfile consistency on the local project's own version

#### Scenario: A contributor adds a new runtime dependency without re-locking
- **WHEN** a PR adds a dependency to `pyproject.toml` but does not include the resulting `uv.lock` change
- **THEN** CI does not catch this (a known tradeoff of `--frozen`); the contributor is responsible per `CONTRIBUTING.md`. The PR review process is the gate.

### Requirement: Codecov upload from a single matrix entry

Coverage upload to Codecov SHALL occur from exactly one matrix entry (currently `runner: ubuntu-24.04`, `python: 3.12`). Other matrix entries SHALL run coverage during their pytest invocation but MUST NOT upload, to avoid mismatched or fragmented coverage reports.

#### Scenario: Test matrix runs
- **WHEN** the matrix expands to ten test jobs
- **THEN** exactly one job (the py3.12 / ubuntu-24.04 entry) executes the codecov-action upload step; the other nine produce coverage reports locally but skip the upload step via an `if:` condition

### Requirement: Local CI replay via `just`

Contributors SHALL have a single command (`just gha-pre-release`) that runs every GitHub Actions job required to safely merge a PR to `main`, sequentially and fail-fast. The recipe SHALL exercise the `secure-workflows.yml`, `release.yml release-please` job, `ci.yml` matrix, and `codeql.yml` workflows under `act` against the same SHAs that CI uses, and SHALL skip workflows that need PR context (`dependency-review.yml`).

#### Scenario: Pre-merge vetting of a Dependabot PR
- **WHEN** a contributor checks out a Dependabot PR locally and runs `just gha-pre-release`
- **THEN** every gating job runs in order; failures abort with a clear message naming the failing workflow

### Requirement: act runner mappings committed via `.actrc`

The repository SHALL contain a committed `.actrc` mapping GitHub-hosted runner labels (`ubuntu-24.04`, `ubuntu-24.04-arm`) to a working Docker image (`catthehacker/ubuntu:act-24.04`). Without this file, `act` silently skips matrix jobs with a `Skipping unsupported platform` message.

#### Scenario: A contributor runs `just test-matrix`
- **WHEN** `act` is invoked with no inline `-P` flags
- **THEN** the runner labels resolve via `.actrc` and the test matrix jobs execute

### Requirement: Dependabot group updates weekly

A `.github/dependabot.yml` configuration SHALL group dependency updates such that related ecosystem bumps land in a single PR per week. Pip group `dev-dependencies` covers `ruff`, `mypy`, `pyright`, `pytest*`, `hypothesis`, `moto*`, `coverage`, `boto3*`. The `github-actions` ecosystem groups all third-party actions.

#### Scenario: Multiple dev-dep updates available
- **WHEN** `ruff` and `mypy` both have new patch releases on the same Monday
- **THEN** Dependabot opens a single PR titled `chore(deps): bump the dev-dependencies group with N updates`, not two separate PRs
