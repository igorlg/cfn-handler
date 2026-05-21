# Proposal: Refactor CI triggers and protect main

## Why

Today every PR-merge cycle runs CI twice: once on the PR, once on the merge commit on `main`. With no branch protection enabled on `main`, that duplicate run is the only thing standing between the codebase and an accidental direct push that bypasses CI entirely. We can do better: gate on PR CI, enforce that PRs pass before merging, and trust `main`.

While we're in the workflow files, two related cleanups: the `cfn-lint` step over example SAM templates is currently bundled into `ci.yml`'s lint job (so every code change re-lints templates that didn't change), and the `secure-workflows.yml` enforcement runs on both PR and `main` push despite only being meaningful on PRs.

This change does not adopt `dorny/paths-filter` for fine-grained per-job change detection — that's a deliberate "first pass" scope. We accept that `ci.yml` still triggers on docs-only PRs in this iteration; a follow-up change will add `dorny` once we've validated the sentinel-aggregator pattern in production.

## What Changes

### Workflow file edits

- **MODIFIED** `.github/workflows/ci.yml`:
  - Remove the `push: branches: [main]` trigger (PR-only).
  - Remove the `cfn-lint over examples` step from the `lint` job (moves to a new workflow).
  - Add a `ci-pass` aggregator job at the end (`if: always()`, `needs: [test, lint]`, succeeds when both dependents are `success` or `skipped`). This becomes the single required status check for branch protection — robust against future path-filter additions.
- **NEW** `.github/workflows/examples-lint.yml`:
  - PR-only, path-filtered to `examples/**` and the workflow file itself.
  - Single job: install `lint` group, run `uv run cfn-lint examples/**/template.yaml`.
  - **Not** required for branch protection (intentional — see design doc).
- **MODIFIED** `.github/workflows/secure-workflows.yml`:
  - Remove the `push: branches: [main]` trigger (PR-only). Path filter on `.github/workflows/**` already in place.
- **MODIFIED** `justfile`:
  - `gha-pre-release` recipe gains a step `3a` that runs `examples-lint.yml` under `act`.
- **MODIFIED** `docs/CI.md`:
  - Reflect the new gating model, sentinel pattern, examples-lint split, and branch protection.

### Repository configuration

- **NEW** branch protection rule on `main`: required status checks = `CI passed`, `analyze (python)`, `review dependencies`, `ensure SHA-pinned actions`. `enforce_admins: false` (admin bypass allowed for releases and emergencies). `required_linear_history: true` (matches squash-merge default). No PR review requirement (solo dev).

### Non-goals

- **No** `dorny/paths-filter` adoption. Deferred to a follow-up change.
- **No** `paths-ignore` on `ci.yml` (would create the "skipped required check" hazard without `dorny`).
- **No** changes to `release.yml`, `dependency-review.yml`, or `codeql.yml` triggers. CodeQL deliberately keeps both push:main and PR triggers because GitHub Code Scanning ties alerts to default-branch runs.
- **No** PR review requirement on branch protection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `ci-infrastructure`: introduced by `document-ci-infrastructure`. This change MODIFIES several requirements (trigger model, lint scope, gating semantics) and ADDS new ones (sentinel aggregator, examples-lint workflow, branch protection on main).

## Impact

- **Code**: workflow YAML edits, one new YAML, justfile recipe step, doc updates.
- **APIs**: zero. No published surface affected.
- **Dependencies**: zero.
- **Systems**:
  - GitHub branch protection becomes active on `main`. After this change ships, direct `git push` to `main` is rejected.
  - Required status checks on PRs gain `CI passed` (the aggregator).
  - Existing workflow names that were previously required (per branch protection) MUST be in the new required-checks list, otherwise PRs will be unmergeable until the protection JSON is updated.
- **Reviewer effort**: moderate. Workflow YAML diffs are easy to read; the branch protection JSON requires care.
- **Migration order**: the workflow changes ship first (backwards-compatible additive), then branch protection is enabled via API as the last step before the PR is merged.
