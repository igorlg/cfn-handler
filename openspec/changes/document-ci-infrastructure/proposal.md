# Proposal: Document CI infrastructure

## Why

The CI and release pipeline has accumulated nuance that is not written down anywhere readable. It lives in inline workflow comments, scattered CONTRIBUTING.md sentences, conversation history, and tribal knowledge. Concrete examples: the SHA-pinning policy and *why* we use commit SHAs rather than annotated-tag SHAs (the lesson from the v1.0.0 release failure); the `--locked` vs `--frozen` choice for `uv sync` and the release-please version-bump drift; the PyPI Trusted Publisher binding and what to do when it fails; the `secure-workflows.yml` enforcement loop; the local-replay tooling (`just gha-pre-release`, `.actrc`, `act` gotchas).

Adding a single `docs/CI.md` reference, plus an `openspec/specs/ci-infrastructure/` capability that captures the requirements as testable assertions, gives future contributors and future-Igor a fighting chance of keeping the pipeline coherent as it evolves.

This change does not modify any CI behaviour. It is the documentation half of the local-CI-replay improvement that landed `.actrc` and the `just gha-pre-release` recipe (PR #7). A separate change (`refactor-ci-triggers-and-protect-main`) follows to actually move the gating model.

## What Changes

### Documentation (user-facing)

- **NEW** `docs/CI.md` (~250-350 lines) covering: workflow inventory, triggers and concurrency, SHA-pinning policy, permissions model, release pipeline (release-please + Trusted Publishing + `uv.lock` drift handling), secrets and environments, Dependabot grouping, local CI replay (`just gha-pre-release`, `.actrc`, `act` notes), branch protection (current state and intended), and a "how to add a new workflow" checklist. Includes a postmortem section on the v1.0.0 release failure as a worked case study.
- **Cross-links** added in `README.md` (near the contributing section) and `CONTRIBUTING.md` (replacing the existing hand-wave) pointing at `docs/CI.md`.

### Specification (capability `ci-infrastructure`)

- **NEW** `openspec/specs/ci-infrastructure/spec.md` formalising the *currently shipped* CI/release behaviour as testable requirements (SHA-pin policy, concurrency policy, lockfile-drift policy, release pipeline, etc.).

### Non-goals

- **No** workflow file changes. Triggers, jobs, permissions stay exactly as-is.
- **No** branch protection enabled. That happens in the follow-up change.
- **No** Dependabot config changes.

## Capabilities

### New Capabilities

- `ci-infrastructure`: the CI/release pipeline, its triggers, gating model, supply-chain hygiene rules, release flow, and local-replay tooling.

### Modified Capabilities

None — `ci-infrastructure` is being introduced; no existing capability is altered.

## Impact

- **Code**: zero. Pure markdown additions.
- **APIs**: zero. No published surface affected.
- **Dependencies**: zero. No deps added or upgraded.
- **Systems**: nothing in CI changes; the docs describe the existing system.
- **Reviewer effort**: significant for `docs/CI.md` (a long-form doc), trivial for the cross-links.
