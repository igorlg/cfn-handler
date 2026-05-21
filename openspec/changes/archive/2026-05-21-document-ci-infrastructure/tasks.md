# Tasks: Document CI infrastructure

## 1. Long-form docs (`docs/CI.md`)

- [x] 1.1 Create `docs/CI.md` with the section structure: Overview, Workflow inventory, Triggers and concurrency, SHA-pinning policy, Permissions model, Release pipeline, Secrets and environments, Dependabot grouping, Local CI replay, Branch protection, Adding a new workflow, Postmortem (v1.0.0 release failure).
- [x] 1.2 Workflow inventory: table with workflow filename, triggers, jobs, purpose, required-for-merge column. Cover `ci.yml`, `codeql.yml`, `dependency-review.yml`, `release.yml`, `secure-workflows.yml`.
- [x] 1.3 Document the SHA-pinning policy: why commit-SHA, why the `# vX.Y.Z` comment, the annotated-tag-SHA failure mode (with the `pypa/gh-action-pypi-publish` example from the v1.0.0 incident).
- [x] 1.4 Document the release pipeline end-to-end: Conventional Commits → release-please PR → squash-merge → tag → wheel build → GitHub Release upload → PyPI Trusted Publishing OIDC. Include the recovery procedure for a failed publish.
- [x] 1.5 Document the `--frozen` vs `--locked` choice and the `uv.lock` drift policy. Reference CONTRIBUTING.md.
- [x] 1.6 Document local CI replay: `just gha-pre-release`, `just test-matrix`, `.actrc`, Apple Silicon `--container-architecture` notes, `gh auth token` for actions that hit the GitHub API.
- [x] 1.7 Document branch protection: current state (disabled) and the intended state (described in the follow-up change). Forward-link to `refactor-ci-triggers-and-protect-main`.
- [x] 1.8 "Adding a new workflow" checklist: SHA-pin every action with a version comment, declare top-level `permissions: contents: read`, escalate per-job, add concurrency group if PR-triggered, document in `docs/CI.md`, ensure `secure-workflows.yml` would still pass.
- [x] 1.9 Postmortem: walk through the v1.0.0 release failure as a worked example (annotated-tag SHA → docker manifest unknown; uv `--locked` vs version bump). Show how `just gha-pre-release` would have caught it.

## 2. Cross-links

- [x] 2.1 Add a "See `docs/CI.md`" pointer in `README.md` near the Contributing section.
- [x] 2.2 Replace the "see CI workflows" hand-wave in `CONTRIBUTING.md` with a link to `docs/CI.md`.

## 3. Spec capture

- [x] 3.1 The capability spec at `openspec/changes/document-ci-infrastructure/specs/ci-infrastructure/spec.md` is authored as part of this change (already drafted in the proposal phase). Verify it accurately reflects the *currently shipped* behaviour, not aspirational state.

## 4. Verification

- [x] 4.1 `openspec validate document-ci-infrastructure --strict` passes.
- [x] 4.2 `just ci-check` passes (sanity: no code change should affect tests).
- [x] 4.3 `markdownlint docs/CI.md` (best effort; no strict gate yet).
- [x] 4.4 Read through the postmortem section carefully — verify all referenced commit SHAs (`6733eb7d…`, `cef221092…`, `9e0d7b8d…`) are accurate per the `release.yml` and `codeql.yml` history.

## 5. Commit and PR

- [x] 5.1 Stage `docs/CI.md`, the README.md and CONTRIBUTING.md cross-link edits, and the openspec change directory. Commit with message `docs(ci): add docs/CI.md and ci-infrastructure spec`.
- [x] 5.2 Push to the existing `feat/gha-pre-release-recipe` branch (PR #7).
- [x] 5.3 Update PR #7's title and body to reflect the expanded scope (now: recipe + .actrc + docs).

## 6. Archive (post-merge)

- [x] 6.1 After PR #7 is merged: `openspec archive document-ci-infrastructure`. Specs move from the change directory to `openspec/specs/ci-infrastructure/`.
