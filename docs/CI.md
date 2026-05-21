# CI/CD reference

This document describes the CI and release infrastructure for `cfn-handler`:
what runs when, why each decision was made, and how contributors replay the
pipeline locally before merging.

> **Note**: this captures the *current* shipped state. A follow-up change
> ([`refactor-ci-triggers-and-protect-main`][next-change]) will move
> `ci.yml` and `secure-workflows.yml` to PR-only triggers, add a sentinel
> aggregator, split `cfn-lint` into its own workflow, and enable branch
> protection on `main`. Update this doc when that lands.

[next-change]: ../openspec/changes/refactor-ci-triggers-and-protect-main/proposal.md

## Overview

Five workflows under `.github/workflows/`:

- **`ci.yml`** — tests, lint, type-check; the main gate.
- **`codeql.yml`** — Python security-and-quality scan.
- **`dependency-review.yml`** — license + vulnerability gate on PRs.
- **`release.yml`** — release-please + PyPI Trusted Publishing OIDC.
- **`secure-workflows.yml`** — enforces commit-SHA pinning of every action.

Plus a Dependabot config (`.github/dependabot.yml`) and an `act` runner
mapping (`.actrc`) at the repo root.

The release pipeline is fully automated: `feat:`/`fix:`/`feat!:` commits drive
[release-please][rp] PRs; merging the release PR builds, tags, uploads to a
GitHub Release, and publishes to PyPI via OIDC ([Trusted Publishers][tp])
with no API tokens stored anywhere.

[rp]: https://github.com/googleapis/release-please
[tp]: https://docs.pypi.org/trusted-publishers/

## Workflow inventory

| File | Triggers | Jobs | Required for merge? |
|---|---|---|---|
| `ci.yml` | `pull_request: main`, `push: main` | matrix `test (py3.10..3.14 × ubuntu-24.04 [+arm])`, `lint + typecheck` | (planned: yes via sentinel) |
| `codeql.yml` | `pull_request: main`, `push: main`, weekly cron | `analyze (python)` | yes |
| `dependency-review.yml` | `pull_request: main` | `review dependencies` | yes |
| `release.yml` | `push: main`, `workflow_dispatch` | `release-please bot`, `build + attach release artifacts`, `publish to PyPI` | n/a (post-merge) |
| `secure-workflows.yml` | `pull_request: main` (paths: `.github/workflows/**`), `push: main` (same paths) | `ensure SHA-pinned actions` | yes (when applicable) |

Note: branch protection is currently **disabled** on `main`; "Required for
merge" reflects intended state once the refactor change lands.

## Triggers and concurrency

### `ci.yml`

- Trigger: PRs against `main` and pushes to `main` (today). Future: PR-only.
- Concurrency:
  ```yaml
  concurrency:
    group: ci-${{ github.ref }}
    cancel-in-progress: ${{ github.event_name == 'pull_request' }}
  ```
  PR runs cancel when superseded by a newer push to the same PR. `main`
  runs are never cancelled — partial test results on `main` are misleading.

### `codeql.yml`

- Trigger: PR + `push: main` + weekly cron (`38 6 * * 2`). The push trigger
  is required because GitHub Code Scanning ties alerts to default-branch
  runs; without it, the security tab never populates. The cron is a
  belt-and-suspenders safety net for periods of low PR activity.

### `release.yml`

- Trigger: `push: main` and `workflow_dispatch`. Manual dispatch lets us
  re-trigger the workflow if a transient error breaks the release pipeline.
  Important: the `publish-pypi` and `publish-artifacts` jobs are gated on
  `release_created == 'true'`, so dispatching the workflow without an
  associated release PR merge is a safe no-op.

### `secure-workflows.yml`

- Trigger: PR + push to `main`, with `paths: ['.github/workflows/**']` on
  both. The path filter saves CI minutes — non-workflow PRs don't trigger
  the SHA-pin checker. Future: PR-only.

### `dependency-review.yml`

- Trigger: PR-only. The action's API requires PR context (base + head SHAs)
  and is not meaningful on a push. Already correct.

## SHA-pinning policy

**Every** third-party action is pinned to a 40-character commit SHA, with
a trailing comment recording the human-readable version:

```yaml
- uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd # v5
- uses: pypa/gh-action-pypi-publish@cef221092ed1bacb1cc03d23a2d87d1d172e277b # v1.14.0
```

Tag pins (e.g. `actions/checkout@v5`) and major-version pins are **not**
permitted. Enforcement runs in `secure-workflows.yml` via
[`zgosalvez/github-actions-ensure-sha-pinned-actions`][zg], which itself
is SHA-pinned.

[zg]: https://github.com/zgosalvez/github-actions-ensure-sha-pinned-actions

### Annotated-tag SHAs vs commit SHAs

Tags in Git can be lightweight (a pointer to a commit) or annotated (an
object of type `tag` that points at a commit). `gh api /repos/<repo>/git/ref/tags/<tag>`
returns the **tag-object SHA** for annotated tags, not the commit SHA.

For JS-based actions, GitHub Actions resolves either to the same checkout,
so this distinction doesn't matter at runtime. **For Docker-based actions
this is fatal**: the action's container image is tagged at `ghcr.io/<repo>:<commit-sha>`,
not at the tag-object SHA. Pinning a Docker action to an annotated-tag SHA
makes the runner fail with `docker: Error response from daemon: manifest unknown`.

This bit us on the first attempt to release v1.0.0 (see [Postmortem](#postmortem-v100-release-failure)).

**To get the commit SHA for a tag**, dereference the tag object:

```bash
# Step 1: get the tag-object SHA
gh api /repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha'

# Step 2: dereference it to the commit SHA
gh api /repos/<owner>/<repo>/git/tags/<sha-from-step-1> --jq '.object.sha'

# Or use git directly:
git ls-remote https://github.com/<owner>/<repo>.git <tag>^{}
```

For non-annotated (lightweight) tags, step 1 already returns the commit
SHA; step 2 returns 404. Always check the `type` field returned by step 1
(`tag` for annotated, `commit` for lightweight).

A simpler heuristic: if Dependabot opens a PR pinning a Docker action to
a different SHA than `gh api .../git/ref/tags/<tag>` returned, trust
Dependabot — it dereferences correctly.

## Permissions model

### Defaults

Every workflow declares a top-level `permissions: contents: read` (or
stricter). Sensitive permissions are escalated **per job**, never at the
workflow level.

### Per-job escalations

| Workflow | Job | Permission | Why |
|---|---|---|---|
| `release.yml` | `release-please bot` | `contents: write`, `pull-requests: write` | create tags, GitHub Releases, open the release PR |
| `release.yml` | `build + attach release artifacts` | `contents: write` | upload wheel/sdist to the GitHub Release |
| `release.yml` | `publish to PyPI` | `id-token: write`, `contents: read` | OIDC token for PyPI Trusted Publishing |
| `codeql.yml` | `analyze (python)` | `security-events: write`, `actions: read`, `contents: read` | upload SARIF results |
| `dependency-review.yml` | `review dependencies` | `contents: read`, `pull-requests: write` | post the optional summary comment |

`id-token: write` is the most sensitive — it lets the job mint OIDC tokens
that can authenticate to PyPI / AWS / etc. It exists in exactly one place
(`publish-pypi`) and is gated behind `if: release_created == 'true'`.

## Release pipeline

```text
feat: / fix: / feat!: commit
              │
              ▼
    push to main   ─────────────────►  release-please-action
                                              │
                                              │ opens or updates a
                                              │ PR titled
                                              │ "chore(main): release X.Y.Z"
                                              ▼
                                       reviewer squash-merges
                                              │
                                              ▼
                                       push to main
                                              │
                                              ▼
                          release.yml ──►  release-please-action
                                              │
                                              │ release_created=true
                                              │ tag_name=vX.Y.Z
                                              ▼
                                       creates git tag + GH Release
                                              │
                          ┌───────────────────┴────────────────────┐
                          ▼                                        ▼
              publish-artifacts                              publish-pypi
              (uv build → gh release upload)                 (uv build → pypa/gh-action-pypi-publish)
                                                                   │
                                                                   │ OIDC token
                                                                   ▼
                                                           PyPI Trusted Publisher
                                                                   │
                                                                   ▼
                                                          wheel + sdist on PyPI
```

### Conventional Commits → version bump

| Commit prefix | Version bump |
|---|---|
| `feat:` | minor |
| `fix:` | patch |
| `feat!:` or footer `BREAKING CHANGE:` | major |
| `chore:`, `ci:`, `docs:`, `refactor:`, `test:`, `style:` | none |

`release-please-action` parses commit titles on `main` since the last
release (per `.release-please-manifest.json`) and proposes the next
version. Squash-merge titles are the source of truth — that's why the
project's `CONTRIBUTING.md` insists on Conventional Commits in PR titles.

### Trusted Publisher binding

Configured **once** at PyPI under Project → Settings → Publishing:

| Field | Value |
|---|---|
| Owner | `igorlg` |
| Repository | `cfn-handler` |
| Workflow filename | `release.yml` |
| Environment name | `pypi` |

This binding is checked on every publish. **It does not depend on action
SHAs** — bumping `pypa/gh-action-pypi-publish` is fine. It depends on the
workflow filename, which is why renaming `release.yml` requires
re-creating the binding on PyPI first.

### Lockfile drift and `--frozen`

`release-please-action` bumps `version` in `pyproject.toml` (and
`.release-please-manifest.json`) but **cannot** also run `uv lock` to
update `uv.lock`. Under `uv sync --locked`, that drift would break every
post-merge CI run on `main` immediately after a release-please merge.

CI uses `uv sync --frozen` instead:

```yaml
- name: Install dependencies
  run: uv sync --frozen --only-group test
```

`--frozen` installs exactly the dependency versions recorded in
`uv.lock`; only the local project's own version is read from the current
`pyproject.toml`. The trade-off: a contributor adding a runtime
dependency to `pyproject.toml` without running `uv lock` will not be
caught by CI — see [Lockfile policy in CONTRIBUTING.md](../CONTRIBUTING.md#lockfile-uvlock).

### Recovery from a failed publish

Symptoms and remediation for the failure modes we've seen:

#### `docker: Error response from daemon: manifest unknown`

Cause: a Docker action (`pypa/gh-action-pypi-publish`) was pinned to its
annotated-tag SHA, not its commit SHA.

Fix: dereference the tag (see [SHA-pinning policy](#sha-pinning-policy))
and update the pin. Then redo the release:

1. Delete the failed tag: `git tag -d vX.Y.Z && git push --delete origin vX.Y.Z`
2. Delete the GitHub Release: `gh release delete vX.Y.Z --yes --cleanup-tag`
3. Reset `.release-please-manifest.json` to the previous version
4. Reset `pyproject.toml` `version` to the previous version
5. Reset `CHANGELOG.md` to the pre-release stub
6. `uv lock` so `uv.lock` matches
7. Push the workflow fix and the resets in a single commit
8. release-please reopens the release PR; merge it; pipeline retries

#### `403 from PyPI` on the `publish-pypi` step

Cause: Trusted Publisher misconfigured (wrong workflow filename, wrong
environment, wrong repo) or never configured.

Fix: configure the publisher at PyPI Project → Settings → Publishing,
matching `release.yml` + environment `pypi` + the correct repo. Then
re-run the failed `publish-pypi` job from the Actions UI.

#### `release_created=false` when expected

Cause: usually a missed prerequisite. Common cases:

- The `chore(main): release X.Y.Z` PR title doesn't match the expected
  pattern (release-please uses the title to recognise its own merges).
- `.release-please-manifest.json` is out of step with the actual git
  history (e.g. a forced revert).
- All commits since the last release are non-bumping (`chore:`, `ci:`,
  etc.) — there's genuinely nothing to release.

Fix: inspect the `release-please bot` job logs for the parse trace; it
prints "Considering N commits" and the bump decision.

## Secrets and environments

### `pypi` environment

Defined under Settings → Environments. Has no protection rules currently
(no required reviewers, no wait timer). The Trusted Publisher binding
references this environment by name — adding wait timers or reviewer
gates here would impose them on every publish.

### Repository secrets

| Secret | Used by | Purpose |
|---|---|---|
| `GITHUB_TOKEN` | every workflow (auto-provisioned) | repo API access |
| `CODECOV_TOKEN` | `ci.yml` upload step | coverage upload |

There is **no** `PYPI_API_TOKEN`. PyPI publishing uses OIDC exclusively.

## Dependabot grouping

Configuration in `.github/dependabot.yml`. Weekly schedule, Mondays.

### `pip` ecosystem (Python deps)

Group `dev-dependencies` covers `ruff`, `mypy`, `pyright`, `pytest*`,
`hypothesis`, `moto*`, `coverage`, `boto3*`. One PR per Monday containing
all bumps in this group; lone PRs only for non-grouped deps.

### `github-actions` ecosystem

Group `github-actions` covers all third-party actions. One PR per Monday
when any action has a new release.

### Why grouping

A bump per dep would mean ~5-10 PRs per Monday. Grouping batches them
into one reviewable diff. The downside (a single bad bump blocks the
group's other bumps) is acceptable because grouped deps are usually
all-or-nothing for our purposes.

## Local CI replay

Three layers of replay, in increasing fidelity:

### `just ci-check` (~10 seconds)

Pure Python — no Docker, no `act`. Runs the same `ruff`, `mypy`, `pyright`,
and `pytest` invocations CI does. Fast inner loop while iterating on code.

### `just test-matrix` (~3-5 minutes)

Runs `ci.yml`'s `test` job under `act` against the full matrix
(`{py3.10..3.14} × {ubuntu-24.04, ubuntu-24.04-arm}`). Validates the
actual job topology, the `setup-uv` action, and emulated arm64 runs on
Apple Silicon. Use after non-trivial workflow changes or to debug
matrix-specific failures.

### `just gha-pre-release` (~5-10 minutes total)

Sequential, fail-fast, **side-effect-free** gate:

1. `secure-workflows.yml` (~5s) — re-validate SHA pinning of every action.
2. **Docker action manifest probe** (~2s) — for every Docker-based action
   referenced in any workflow, verify that `ghcr.io/<repo>:<sha>` actually
   resolves to a published image. This is the targeted defence against
   the v1.0.0 release-failure bug class (annotated-tag-SHA on a Docker
   action). Catches it locally in seconds.
3a. `ci.yml` test matrix (~3-5 min) via `just test-matrix` — `act -j test`
    against amd64 + arm64 × 5 Python versions in parallel.
3b. `ci.yml` lint+typecheck job (~30s) — `act -j lint` runs ruff,
    ruff format check, mypy strict, pyright strict, and cfn-lint over
    examples. Yes, lint is a separate `act` invocation: `act -j test`
    only selects the test job, so without 3b a lint-only failure would
    sneak through the gate.
4. `codeql.yml` (~1-8min depending on bundle cache) — Python
   security-and-quality scan.

Skips `dependency-review.yml` (needs PR context that `act` can't synthesize).

**Notably absent**: an `act` run of `release.yml`. An earlier iteration
of this recipe ran `release.yml`'s `release-please` job locally; Codex
review correctly flagged that this had real side effects (running
`release-please-action` with the user's `gh auth token` against the
actual repo can open or update real release PRs). The Docker-manifest
probe in step 2 catches the bug class we cared about (the v1.0.0
incident) without invoking `release.yml` at all, and is far faster.

This is the recommended pre-merge ritual for **dependency-bump PRs**.

### `act` mappings (`.actrc`)

Two `-P` flags map GitHub-hosted runner labels to a Docker image:

```text
-P ubuntu-24.04=catthehacker/ubuntu:act-24.04
-P ubuntu-24.04-arm=catthehacker/ubuntu:act-24.04
```

Without these, `act` silently skips matrix jobs with `Skipping unsupported
platform`. Both labels point at the same image; the actual emulation
arch is selected per recipe via `--container-architecture`.

### Apple Silicon notes

- Always pass `--container-architecture linux/amd64` (or `linux/arm64`)
  on M-series. Without it, `act` warns and may skip jobs.
- Native arm64 emulation is faster on Apple Silicon than QEMU-emulated
  amd64. `just test-matrix-arm64` is preferable for fast iteration.
- The `UV_LINK_MODE=copy` env in `ci.yml` silences a hardlink warning
  when `act` mounts the workspace across filesystems. Don't override.

### `gh auth token` for actions that need GitHub API

`release-please-action` and `actions/dependency-review-action` call the
GitHub API. `act` needs a token to authenticate:

```bash
act push -W .github/workflows/release.yml \
  --secret GITHUB_TOKEN="$(gh auth token)"
```

The `gha-pre-release` recipe handles this transparently.

## Branch protection

**Currently disabled.** This is a transitional state; the
[`refactor-ci-triggers-and-protect-main`][next-change] change enables it.

When enabled, the rule on `main` will require:

- `CI passed` — sentinel aggregator from `ci.yml`
- `analyze (python)` — CodeQL
- `review dependencies` — dependency-review-action
- `ensure SHA-pinned actions` — secure-workflows zgosalvez

With `enforce_admins: false` (admin bypass for emergencies),
`required_linear_history: true`, no PR review requirement (solo dev),
no force-push, no deletion. The reproducible `gh api -X PUT` JSON
will live in that change's `tasks.md` migration plan.

## Adding a new workflow

Checklist before opening the PR:

- [ ] **SHA-pin every `uses:`** with a trailing `# vX.Y.Z` comment.
      `secure-workflows.yml` will fail your PR otherwise.
- [ ] **Use commit SHAs**, not annotated-tag SHAs. For Docker actions
      this is mandatory; for JS actions it works either way but stay
      consistent.
- [ ] **Top-level `permissions: contents: read`** (or stricter).
      Escalate per-job only.
- [ ] **`id-token: write`** only if the job actually uses OIDC (PyPI,
      AWS STS, etc.). Document why in a comment.
- [ ] **Concurrency group** if PR-triggered: `concurrency.group: <name>-${{ github.ref }}`,
      `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`.
- [ ] **Path filters** if the workflow only cares about specific files.
      Be aware of the [required-check + skipped-check][gh-skipped] hazard
      if the workflow is required for merge.
- [ ] **Document in this file**: add a row to "Workflow inventory", and
      explain the trigger rationale in "Triggers and concurrency".
- [ ] If you added a new **job to `ci.yml`**, also add it to `ci-pass`'s
      `needs:` list (when the sentinel lands). Otherwise the aggregator
      reports green even when your job fails.
- [ ] Run `just gha-pre-release` locally to verify before pushing.

[gh-skipped]: https://github.com/orgs/community/discussions/13690

## Postmortem: v1.0.0 release failure

The first attempt to release `cfn-handler 1.0.0` failed with two
compounding bugs. Useful as a worked example of how the supply-chain
hygiene policies above came to exist.

### Timeline

1. Release-please PR `chore(main): release 1.0.0` was squash-merged.
2. `release.yml` triggered:
   - `release-please bot` ✓ — created tag `v1.0.0`
   - `build + attach release artifacts` ✓ — built wheel/sdist, uploaded to GH Release
   - `publish to PyPI` ✗ — `docker: Error response from daemon: manifest unknown`
3. Simultaneously, `ci.yml` on the same merge commit failed:
   - `uv sync --locked` rejected the merge: `The lockfile at uv.lock needs to be updated, but --locked was provided`

### Root cause #1: annotated-tag SHA on a Docker action

The pin in `release.yml` was:

```yaml
- uses: pypa/gh-action-pypi-publish@6733eb7d741f0b11ec6a39b58540dab7590f9b7d # v1.14.0
```

`6733eb7d…` was the **tag-object SHA** for the v1.14.0 annotated tag,
not the commit SHA. `pypa/gh-action-pypi-publish` is a Docker action;
the runner does `docker pull ghcr.io/pypa/gh-action-pypi-publish:6733eb7d…`,
finds no image at that tag, and exits.

The correct pin is the commit SHA `cef221092ed1bacb1cc03d23a2d87d1d172e277b`.
This is what Dependabot would have proposed (and did, in a follow-up PR).

**Lesson**: SHA-pinning is necessary but not sufficient — the SHA must be a commit SHA.

### Root cause #2: `--locked` vs release-please version bump

`ci.yml` ran `uv sync --locked --only-group test`. The merge commit had
`pyproject.toml: version = "1.0.0"` (release-please's bump) but
`uv.lock` still listed `cfn-handler==0.0.0`. `--locked` rejects any
divergence, including the local project's own version.

This was always going to break on the first release-please merge. CI on
PRs ran on the bot's release-please branch, where the same drift
existed, but those CI runs are short-circuited by GitHub's
`secrets.GITHUB_TOKEN` not triggering follow-up PR-triggered workflows
on bot-authored branches — so the failure didn't surface pre-merge.

### What we changed

1. Repinned `pypa/gh-action-pypi-publish` to its commit SHA.
2. Switched `ci.yml` to `uv sync --frozen` (lockfile authoritative for
   deps, project version read from current `pyproject.toml`).
3. Reset the release-please state (manifest 1.0.0 → 0.0.0, pyproject
   1.0.0 → 0.0.0, CHANGELOG.md to stub, deleted v1.0.0 tag and Release).
4. Re-merged the release PR after the fixes were on `main`.

The retry succeeded; v1.0.0 published to PyPI.

### What would have caught it pre-merge

`just gha-pre-release` (added in the same PR cycle as this doc) runs a
**Docker-manifest probe** as step 2: for every Docker-based action
referenced in any workflow, it does a `docker manifest inspect ghcr.io/<repo>:<sha>`
and fails fast if the SHA does not resolve to a real image. This is a
direct, side-effect-free check of exactly the bug class that broke us
— no need to invoke `release.yml` (which would itself have side
effects on the repo).

The `--locked` failure would have surfaced post-merge CI on `main`
either way, but CONTRIBUTING.md's lockfile-policy section now warns
contributors to manually `uv lock` after dependency edits. The release-
please case is unrecoverable without manual reset, which is the failure
mode this postmortem describes.

---

For the broader contribution workflow (commit conventions, branching,
local checks), see [CONTRIBUTING.md](../CONTRIBUTING.md). For library
behaviour specs, see `openspec/specs/`.
