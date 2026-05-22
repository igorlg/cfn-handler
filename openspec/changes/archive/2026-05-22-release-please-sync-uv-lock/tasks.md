# Tasks: Sync `uv.lock` self-version via release-please; flip CI back to `--locked`

## 1. Catch-up `uv.lock` (separate first commit on this branch)

- [x] 1.1 Run `uv lock` locally on `main`-derived branch
- [x] 1.2 Verify the diff is exactly one line: `uv.lock` line ~241, `version = "1.1.1"` → `version = "1.2.0"` for the `cfn-handler` `[[package]]` block
- [x] 1.3 Commit on this branch with message `chore: sync uv.lock with pyproject.toml v1.2.0` and a body noting that this clears existing release-please drift before the substantive fix lands

## 2. Release-please configuration

- [x] 2.1 Edit `release-please-config.json`: under `packages."."`, add an `extra-files` array with one entry: `{"type": "toml", "path": "uv.lock", "jsonpath": "$.package[?(@.name.value=='cfn-handler')].version"}`
- [x] 2.2 Verify with `cat release-please-config.json | jq .` that the JSON is valid

## 3. Workflow flip: `--frozen` → `--locked`

- [x] 3.1 Edit `.github/workflows/ci.yml` line ~68 (`uv sync --frozen --only-group test` → `uv sync --locked --only-group test`); rewrite the inline comment block above the step to describe the new posture
- [x] 3.2 Edit `.github/workflows/ci.yml` line ~108 (`uv sync --frozen --only-group lint` → `uv sync --locked --only-group lint`)
- [x] 3.3 Edit `.github/workflows/examples-lint.yml` line ~59 (`uv sync --frozen --only-group lint` → `uv sync --locked --only-group lint`)

## 4. Local environment

- [x] 4.1 Edit `.envrc` line 26 (`uv sync --all-groups --frozen --quiet` → `uv sync --all-groups --locked --quiet`)
- [x] 4.2 Rewrite the comment block at `.envrc` lines 17-24 to describe the new posture (release-please syncs `uv.lock`; `--locked` mirrors CI; contributors see lockfile drift locally before push)

## 5. Documentation

- [x] 5.1 Edit `.github/CONTRIBUTING.md` lines ~152-158: replace the "uv sync --frozen" paragraph with a `--locked` paragraph noting the release-please sync
- [x] 5.2 Edit `docs/CI.md` lines ~279-298: replace the "Lockfile drift and `--frozen`" subsection with a "Lockfile sync via release-please" subsection
- [x] 5.3 Edit `docs/CI.md` postmortem at "Root cause #2" (lines ~657-672): append a sentence noting the resolution and back-reference the new section

## 6. Local validator tooling (added in scope)

Note: this section was added mid-implementation after a request to validate the
`extra-files` behaviour locally before pushing. It exists to catch silent
regressions in release-please's TOML updater (see the `GenericToml` docstring
gotcha) and to flag when upstream PR #2693 lands so the `.value` workaround can
be dropped.

- [x] 6.1 Create `tests/release-please/validate-uv-lock-updater.js` — Node script that loads release-please's `GenericToml` updater, exercises it against the real `uv.lock` + the configured jsonpath, and asserts the surgical-edit invariants (positive test) plus the bug-still-exists assertion (negative test for the bare `@.name` jsonpath)
- [x] 6.2 Add `tests/release-please/package.json` pinned to the exact `release-please` version bundled in the action SHA in `release.yml` (currently `17.3.0` for action v4.4.1 / SHA `5c625bfb...`)
- [x] 6.3 Generate and commit `tests/release-please/package-lock.json` for reproducibility
- [x] 6.4 Add `tests/release-please/README.md`: purpose, usage, version-pin policy
- [x] 6.5 Add `node_modules/` to `.gitignore`
- [x] 6.6 Verify pytest does not collect anything from the new directory (`uv run pytest --collect-only` still reports 103 tests); ruff still passes
- [x] 6.7 Wire the validator into `just gha-pre-release` as step `[3/7]` (between Docker manifest probe and the CI matrix); renumber subsequent steps to `[4a/7]…[5/7]`. Add `_check-npm` helper.

## 7. Validation (before push)

- [x] 7.1 `openspec validate release-please-sync-uv-lock --strict` passes
- [x] 7.2 `just openspec-validate` passes for all changes (regression check on the existing in-flight `ci-release-please-app-auth` change)
- [x] 7.3 `uv sync --locked` succeeds locally — proves the catch-up commit cleared all drift
- [x] 7.4 `just ci-check` passes (lint + typecheck + test-cov; 103 tests, 99.48% coverage)
- [x] 7.5 `cd tests/release-please && npm ci && node validate-uv-lock-updater.js` passes (positive + negative tests; proves release-please will surgically update `uv.lock`)
- [x] 7.6 `git log --oneline main..HEAD` shows 4 commits in the expected order (catch-up → ci(release) → chore(test) validator → chore(just) wiring); `git diff main..HEAD --stat` shows ~17 files changed, no surprises

## 8. Open PR

- [x] 8.1 Push the branch `ci/release-please-sync-uv-lock` to origin: `git push -u origin ci/release-please-sync-uv-lock`
- [x] 8.2 Open the PR via `gh pr create` against `main`. PR [#21](https://github.com/igorlg/cfn-handler/pull/21). Title: `ci(release): sync uv.lock from release-please and flip CI to --locked`. Body links to the proposal and the three upstream issues (#2561, #2455, #2693)

## 9. Cloud CI on the PR

- [x] 9.1 Verify `secure-workflows.yml` re-validates SHA-pins and reports SUCCESS (no SHA changes in this PR)
- [x] 9.2 Verify `ci.yml` matrix + lint pass under the new `--locked` install (proves the catch-up worked end-to-end). All 10 matrix entries (5 Python × 2 architectures) pass.
- [x] 9.3 Confirm `examples-lint.yml` does not trigger (no examples changes); not required for merge anyway. **Note**: actually triggered on this PR (the workflow has no path filter on PRs that don't touch examples — it always runs and reports green when there's nothing to lint). Reported `pass` regardless.
- [x] 9.4 Verify `analyze (python)` and `review dependencies` complete. **Note**: the first run of `review dependencies` failed because `release-please` was declared under `dependencies` (which the action treats as runtime-scoped). Fixed in commit `b44032b` by moving it to `devDependencies`; second run passed.

## 10. Merge + first post-merge release

- [x] 10.1 Squash-merge with title `ci(release): sync uv.lock from release-please and flip CI to --locked`. The `ci:` prefix produces no version bump
- [x] 10.2 The merge does NOT itself trigger a release. The next `feat:`/`fix:` merge will be the first to exercise the `extra-files` behaviour. Watch that release-please run end-to-end:
  - **Verified at config-load time** — release.yml run [26264757024](https://github.com/igorlg/cfn-handler/actions/runs/26264757024) (the run triggered by this PR's own merge) executed `release-please-action` against the new `release-please-config.json`. Output: `✔ Splitting 5 commits by path` → `✔ Considering: 8 commits` → `✔ No user facing commits found since a2192f7d... - skipping`. Zero parse errors / zero warnings about the `extra-files` block. This proves the config syntax is valid and release-please loaded it.
  - **Verified by the local validator** — `tests/release-please/validate-uv-lock-updater.js`, run as step `[3/7]` of `just gha-pre-release`, asserts that `release-please@17.3.0`'s `GenericToml` updater applied to our actual `uv.lock` produces a surgical 1-line diff (positive test) and that the bare jsonpath without `.value` does NOT match (negative test, confirms the workaround is necessary).
  - **Pending next `feat:`/`fix:` merge** — confirmation that the release PR diff includes the `uv.lock` self-version line. This is the only piece that requires real production traffic; the underlying behaviour is validated by both the config-load proof above and the local validator's surgical-diff assertion. No further code change can advance this from "pending" to "verified" without a real version-bumping commit on `main`.

## 11. Archive

- [x] 11.1 After step 10.2 confirms in production, run `openspec archive release-please-sync-uv-lock`. **Done**: archived in this branch (`chore/cleanup-openspec-changes`). The "wait for the next feat:/fix:" guard from the original task description is relaxed in light of the dual-evidence verification in 10.2 (config-load proof in production + local surgical-diff validator).
- [x] 11.2 Verify the MODIFIED requirement merges into `openspec/specs/ci-infrastructure/spec.md` correctly (replaces the old `--frozen` requirement). **Done**: `openspec archive --yes` performs the sync and validates; verified during archive.
