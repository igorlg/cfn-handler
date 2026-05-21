# Design: Document CI infrastructure

## Context

This is a documentation-only change. The CI/release pipeline already exists and works; this change just captures it in `docs/CI.md` and a new `ci-infrastructure` capability spec. No architectural decisions are being made here — see `proposal.md` for the rationale and the spec for the as-built requirements.

## Goals / Non-Goals

**Goals:**
- Single source of truth for CI/release behaviour at `docs/CI.md`.
- Testable requirements at `openspec/specs/ci-infrastructure/spec.md`.
- Cross-links from `README.md` and `CONTRIBUTING.md` so the doc is discoverable.

**Non-Goals:**
- Any change to workflow behaviour, triggers, jobs, or permissions.
- Branch protection (deferred to `refactor-ci-triggers-and-protect-main`).
- New tooling.

## Decisions

### D1 — Doc location: `docs/CI.md`

Considered `CONTRIBUTING.md` (too long for a generic contributing doc), `.github/README.md` (renders as a directory README on GitHub, awkward for long-form), and a top-level `CI.md` (clutters root). Selected `docs/CI.md` because it scales: future docs (architecture, release process, security policy elaborations) can live alongside without polluting the repo root. README.md gets a short "see `docs/CI.md`" pointer.

### D2 — Spec capability name: `ci-infrastructure`

Considered `release-pipeline`, `ci-pipeline`, `gha-infrastructure`. Selected `ci-infrastructure` because it covers both the testing pipeline and the release pipeline; the next change will modify gating semantics and we want a single capability rather than fragmenting. The `refactor-ci-triggers-and-protect-main` change will MODIFY this same capability.

## Risks / Trade-offs

- **[Risk] Long doc rots if not maintained.** → Mitigation: every workflow PR's checklist (per CI.md itself) requires updating CI.md when triggers, permissions, or supply-chain rules change. The `ci-infrastructure` spec acts as a forcing function: changing CI without updating the spec will fail `openspec validate`.
- **[Trade-off] Spec captures *current* behaviour, including imperfections we plan to fix.** → Acceptable. The follow-up change (`refactor-ci-triggers-and-protect-main`) is already proposed and will update the spec when it ships. Documenting the as-built state honestly is more useful than aspirational text.

## Migration Plan

None — this change adds files only. Rollback is `git revert`.

## Open Questions

None.
