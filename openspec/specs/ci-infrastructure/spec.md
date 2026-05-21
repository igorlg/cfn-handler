# ci-infrastructure Specification

## Purpose
TBD - created by archiving change document-ci-infrastructure. Update Purpose after archive.
## Requirements
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

Every workflow file SHALL declare a top-level `permissions: contents: read` (or stricter) and SHALL escalate permissions only on jobs that genuinely need them. Sensitive permissions — `id-token: write`, `contents: write`, `pull-requests: write` — MUST appear at the job level, never at the workflow level. The new `examples-lint.yml` workflow SHALL set `permissions: contents: read` and not escalate.

#### Scenario: A job needs to publish to PyPI via OIDC
- **WHEN** the `publish-pypi` job in `release.yml` runs
- **THEN** it has `id-token: write` declared at the job level; other jobs in the same workflow do NOT have that permission

#### Scenario: A job needs to create a tag and a GitHub Release
- **WHEN** the `release-please` job in `release.yml` runs
- **THEN** it has `contents: write` and `pull-requests: write` declared at the job level; other workflow jobs default to `contents: read`

#### Scenario: examples-lint runs
- **WHEN** the `cfn-lint` job in `examples-lint.yml` runs
- **THEN** the workflow declares `permissions: contents: read` at the top level; the job does not escalate (cfn-lint reads `examples/` and exits)

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

Contributors SHALL have a single command (`just gha-pre-release`) that runs every GitHub Actions job required to safely merge a PR to `main`, sequentially and fail-fast. The recipe SHALL exercise the `secure-workflows.yml`, `release.yml release-please` job, `ci.yml` matrix, `examples-lint.yml`, and `codeql.yml` workflows under `act` against the same SHAs that CI uses, and SHALL skip workflows that need PR context (`dependency-review.yml`).

#### Scenario: Pre-merge vetting of a Dependabot PR
- **WHEN** a contributor checks out a Dependabot PR locally and runs `just gha-pre-release`
- **THEN** every gating job runs in order; failures abort with a clear message naming the failing workflow

#### Scenario: A PR includes example template changes
- **WHEN** a contributor's branch modifies `examples/basic/template.yaml`
- **THEN** `just gha-pre-release` runs `examples-lint.yml` as a dedicated step in the sequence and reports cfn-lint failures inline

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

### Requirement: PR-only gating for `ci.yml` and `secure-workflows.yml`

Both `ci.yml` and `secure-workflows.yml` SHALL trigger only on `pull_request: branches: [main]`. The `push: branches: [main]` trigger SHALL be removed from both. With branch protection requiring CI to pass before merging, the post-merge `main` run was redundant; removing it eliminates duplicate runs and clarifies the gating model: PR is the gate, `main` is trusted.

#### Scenario: A new PR is opened against main
- **WHEN** a contributor opens or pushes to a PR with base `main`
- **THEN** `ci.yml` triggers and runs the test matrix, the lint+typecheck job, and the `ci-pass` aggregator

#### Scenario: A PR is squash-merged to main
- **WHEN** the PR's `chore(...)` or `feat(...)` commit is squash-merged onto `main`
- **THEN** `ci.yml` does NOT trigger on the resulting `main` push (no duplicate run); `release.yml` still triggers because it remains main-only as the release driver

### Requirement: `ci-pass` sentinel aggregator job

`ci.yml` SHALL include a job named `CI passed` (job id `ci-pass`) at the end of the workflow that depends on every other CI job via `needs: [test, lint]`. The job SHALL run with `if: always()` so it executes regardless of dependency status, and SHALL exit success only when every dependency's `result` is `success` or `skipped`. Failure or cancellation in any dependency causes the aggregator to fail.

The aggregator becomes the SINGLE required status check for the test+lint surface in branch protection. This makes the configuration robust to matrix changes (no need to update the required-check list when adding or removing Python versions, runners, or supplementary jobs).

#### Scenario: All matrix entries pass
- **WHEN** all 10 matrix `test` entries and the `lint + typecheck` job complete with `success`
- **THEN** `CI passed` succeeds; branch protection sees a green check

#### Scenario: One matrix entry fails
- **WHEN** any single matrix entry fails (e.g. `test (py3.14 / ubuntu-24.04-arm)`)
- **THEN** `needs.test.result` is `failure`; `CI passed` exits 1; branch protection blocks merge

#### Scenario: A future job is added to ci.yml but not to the aggregator's needs
- **WHEN** a developer adds a new job `foo:` to `ci.yml` but forgets to add `foo` to `ci-pass`'s `needs:` list
- **THEN** `CI passed` reports green even if `foo` fails; this is a known foot-gun, documented in `docs/CI.md`'s "Adding a new workflow" checklist

### Requirement: Standalone `examples-lint.yml` workflow (informational)

A separate workflow `examples-lint.yml` SHALL exist for running `cfn-lint` over example SAM templates. It SHALL trigger only on PRs and SHALL be path-filtered to `examples/**` and `.github/workflows/examples-lint.yml`. The `cfn-lint over examples` step SHALL be REMOVED from `ci.yml`'s `lint` job.

This workflow SHALL NOT be a required status check for branch protection. The reason is technical: a path-filtered workflow does not trigger on PRs that don't touch the filtered paths, and GitHub branch protection treats a missing required check as not-green, blocking merges. Until `dorny/paths-filter`-driven sentinels are adopted (deferred follow-up), `examples-lint` is informational: a broken example template shows a red X on the PR but does not block the merge.

#### Scenario: A PR modifies an example template
- **WHEN** a PR modifies `examples/basic/template.yaml`
- **THEN** `examples-lint.yml` triggers, runs `uv run cfn-lint examples/**/template.yaml`, and reports a status check on the PR

#### Scenario: A PR does not touch examples
- **WHEN** a PR modifies only `src/cfn_handler/`
- **THEN** `examples-lint.yml` does not trigger; no `examples-lint` status check appears on the PR; branch protection is unaffected

#### Scenario: An example template has a cfn-lint error
- **WHEN** a PR introduces an invalid SAM resource into `examples/polled/template.yaml`
- **THEN** `examples-lint.yml` reports `failure` on the PR; the PR remains mergeable (not a required check); reviewers see the red X and decide whether to block manually

### Requirement: Branch protection enabled on `main`

The `main` branch SHALL have a branch protection rule enabled with the following required status checks:

- `CI passed` — the sentinel aggregator from `ci.yml`
- `analyze (python)` — from `codeql.yml`
- `review dependencies` — from `dependency-review.yml`
- `ensure SHA-pinned actions` — from `secure-workflows.yml`

Additional protection settings:
- `strict: true` — require branches up-to-date before merge
- `enforce_admins: false` — admin bypass allowed for releases and emergencies
- `required_pull_request_reviews: null` — no review requirement (solo dev pattern; would self-block PRs)
- `required_linear_history: true` — matches the squash-merge convention; disallows merge commits
- `allow_force_pushes: false`
- `allow_deletions: false`

#### Scenario: Direct push to main without admin bypass
- **WHEN** a contributor without admin privileges attempts `git push origin main`
- **THEN** GitHub rejects the push with a branch-protection-rule-violation error

#### Scenario: PR with failing CI
- **WHEN** a PR's `CI passed` status check is `failure`
- **THEN** the GitHub merge button is disabled; merging requires `gh pr merge --admin` and only succeeds for admins

#### Scenario: PR with stale base
- **WHEN** a PR's base branch is behind `main` (because a different PR merged after this PR opened)
- **THEN** GitHub displays "This branch is out-of-date with the base branch" and the merge button is disabled until the PR is updated

#### Scenario: Admin needs to push during CI outage
- **WHEN** the maintainer (admin) needs to push directly to `main` to repair a broken state (e.g. rollback)
- **THEN** the push succeeds because `enforce_admins: false`; this is the documented escape hatch

