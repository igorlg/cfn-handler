# Design: Refactor CI triggers and protect main

## Context

The CI gating model evolved organically: `ci.yml` and `codeql.yml` triggered on both `pull_request: main` and `push: main`, providing two layers of safety net at the cost of duplicate runs after every merge. With `main` unprotected today, the post-merge re-run is the only barrier against an accidental direct push. We can collapse that into a single, cleaner model: PR CI is the gate; `main` is protected; merge means safe.

The `secure-workflows.yml` enforcement sits awkwardly: it runs on `push: main` (after merge — too late to block bad SHA pins) and on PR (correctly gating). PR-only is the right scope.

`cfn-lint` over the example SAM templates is currently embedded in `ci.yml`'s lint job, meaning every `src/` change triggers a re-lint of templates that didn't change. Moving it out into `examples-lint.yml` with a `paths` filter on `examples/**` saves ~10 seconds per non-examples PR and produces a clearer signal when an example template breaks.

The wrinkle: GitHub branch protection's "required status check" interaction with `paths`-filtered workflows is broken by design. If `examples-lint.yml` is path-filtered and a PR doesn't touch `examples/**`, the workflow doesn't trigger and the check is reported as "missing", which branch protection treats as not-green, blocking the merge. The mature solution is `dorny/paths-filter` driving a single sentinel job; the simpler "first pass" solution is the **sentinel aggregator** pattern: a single `ci-pass` job that depends on every other CI job and reports success if all dependents are `success` or `skipped`. We adopt the sentinel pattern in `ci.yml` and accept that `examples-lint.yml` is informational (not required) until we add `dorny`.

## Goals / Non-Goals

**Goals:**
- `ci.yml` runs only on PRs (no duplicate post-merge run).
- `secure-workflows.yml` runs only on PRs.
- Branch protection on `main` blocks accidental direct pushes.
- A single required status check (`CI passed`) gates the test+lint surface, robust to future path filters.
- `cfn-lint` lives in its own workflow with appropriate path filtering.
- `just gha-pre-release` exercises the new `examples-lint.yml` too.

**Non-Goals:**
- `dorny/paths-filter`-based fine-grained job conditioning. Deferred.
- `paths-ignore` on `ci.yml`. Without `dorny`, this would create the "skipped required check" hazard.
- Required PR review (solo dev pattern; review requirement would be self-blocking).
- Changes to `release.yml`, `dependency-review.yml`, or `codeql.yml` triggers.

## Decisions

### D1 — Sentinel aggregator (`ci-pass`) over `dorny/paths-filter`

`dorny/paths-filter` is the canonical solution for path-aware required checks. We deliberately defer it: this is our first time using a sentinel-aggregator pattern in production, and the failure mode of an over-clever job-conditioning system is worse than running CI on a docs-only PR. The sentinel pattern is ~10 lines of inline shell, no new dependencies, no new SHA to pin. Once we've lived with branch protection for a couple of weeks and know it behaves well, a follow-up change introduces `dorny` and tightens the path filters across `ci.yml` and `examples-lint.yml`.

The aggregator is a tiny job:

```yaml
ci-pass:
  name: CI passed
  if: always()
  needs: [test, lint]
  runs-on: ubuntu-24.04
  steps:
    - name: All required jobs passed (or were skipped)
      env:
        TEST_RESULT: ${{ needs.test.result }}
        LINT_RESULT: ${{ needs.lint.result }}
      run: |
        for r in "$TEST_RESULT" "$LINT_RESULT"; do
          [[ "$r" == "success" || "$r" == "skipped" ]] || exit 1
        done
        echo "All CI jobs passed."
```

Rejected alternatives:
- `re-actors/alls-green`: a third-party action doing exactly this. Adds a SHA-pin and a dependency for ~10 lines of shell. Inline wins on simplicity.
- Multiple required checks (`test (py3.10 / ubuntu-24.04)`, …, `lint + typecheck`): brittle as the matrix evolves; renaming a job silently breaks branch protection.

### D2 — `examples-lint.yml` not required for branch protection

Path-filtered workflows can't be reliably required without `dorny`. Three options were considered:
- **Make required, no path filter** → wastes ~30s on every non-examples PR.
- **Make required, path filter** → blocks every non-examples PR (check missing).
- **Not required, path filter** → fast, broken example templates show red but don't block merge.

Examples are pedagogical SAM stacks, not production code. A broken template is annoying but not user-facing. We pick option 3 (not required); when `dorny` lands, we promote `examples-lint` to required via a sentinel.

### D3 — Keep `codeql.yml` dual-trigger

GitHub's Code Scanning ties alerts to the default branch. If CodeQL only runs on PRs, the security tab never populates main-branch alerts and the alert UI shows nothing. PR runs additionally catch issues pre-merge. The cost is a minute of CI time per `main` push — well worth it.

### D4 — Branch protection: admin bypass enabled, linear history required

`enforce_admins: false` is the sober default for solo development: when something legitimate needs to ship around the gate (a release-please merge during PyPI outage; a critical security fix during CI breakage), admin bypass exists. The `required_linear_history: true` setting matches our squash-merge default — it disallows merge commits, which is correct for the project's conventional-commits-driven release flow.

No PR review requirement: a solo developer can't approve their own PR, so requiring reviews would block every PR.

### D5 — Required status checks list

The full required-checks set on `main`:
- `CI passed` (the new sentinel aggregator)
- `analyze (python)` (CodeQL)
- `review dependencies` (dependency-review-action)
- `ensure SHA-pinned actions` (secure-workflows zgosalvez)

Notably absent: any individual matrix job, any `examples-lint` check, any `release.yml` job (release.yml runs after merge, not before). The aggregator captures the matrix transitively.

### D6 — Migration order: ship workflow YAML first, enable protection last

The PR is structured so the workflow changes are reviewable and mergeable on their own. Branch protection is enabled via `gh api` as the FINAL task before merging, AFTER the new `CI passed` check name has appeared at least once on `main`'s history (so GitHub knows the check name exists). Ordering wrong (protection first, then workflow merge) creates a window where the required check `CI passed` doesn't exist yet, and PRs are unmergeable.

## Risks / Trade-offs

- **[Risk] Required-check misconfiguration blocks all merges.** → Mitigation: `enforce_admins: false` lets the maintainer push directly to repair. The protection JSON is committed to a script in `docs/CI.md` so it's reproducible.
- **[Risk] `examples-lint` failure goes unnoticed because not required.** → Mitigation: it still shows as a red X on the PR; reviewers see it. Documented in `docs/CI.md`. Promoted to required when `dorny` lands.
- **[Risk] Sentinel pattern fails open if we forget to add a new job to `needs:`.** → Mitigation: documented in `docs/CI.md`'s "Adding a new workflow" checklist. Future audit could be a `secure-workflows.yml`-style job that enforces all CI jobs are listed in `needs:`.
- **[Trade-off] Docs-only PRs still trigger `ci.yml`.** → Acceptable for first pass; ~3-5 min of CI time saved per docs PR is the explicit prize the `dorny` follow-up earns.
- **[Trade-off] Removing `cfn-lint` from `ci.yml` means it no longer runs on `pyproject.toml`-only PRs that change cfn-lint config.** → Negligible. cfn-lint config is currently default; if we ever add a `.cfnlintrc.yaml`, that file is in `examples-lint.yml`'s path filter.

## Migration Plan

Sequential steps in the PR's task list:

1. Edit `.github/workflows/ci.yml`: drop `push: main` trigger, remove `cfn-lint over examples` step, add `ci-pass` aggregator.
2. Create `.github/workflows/examples-lint.yml`.
3. Edit `.github/workflows/secure-workflows.yml`: drop `push: main` trigger.
4. Update `justfile` `gha-pre-release` recipe: add step `3a` for `examples-lint.yml`.
5. Update `docs/CI.md`: reflect new gating model, sentinel pattern, examples-lint split, branch protection.
6. Run `just gha-pre-release` locally and confirm green.
7. Open PR; cloud CI runs (now PR-only); confirm green.
8. **Branch protection enabled via `gh api -X PUT`** with the JSON committed in the `docs/CI.md` migration plan section. This is the irreversible step.
9. Squash-merge the PR.
10. Verify a direct `git push` to `main` is now rejected.

Rollback: `gh api -X DELETE /repos/igorlg/cfn-handler/branches/main/protection` reverts protection. The workflow YAML changes are reverted via `git revert`.

## Open Questions

None. The dorny follow-up is intentionally out-of-scope.
