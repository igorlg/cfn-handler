# Tasks: Sync `uv.lock` self-version via release-please; flip CI back to `--locked`

## 1. Catch-up `uv.lock` (separate first commit on this branch)

- [x] 1.1 Run `uv lock` locally on `main`-derived branch
- [x] 1.2 Verify the diff is exactly one line: `uv.lock` line ~241, `version = "1.1.1"` → `version = "1.2.0"` for the `cfn-handler` `[[package]]` block
- [x] 1.3 Commit on this branch with message `chore: sync uv.lock with pyproject.toml v1.2.0` and a body noting that this clears existing release-please drift before the substantive fix lands

## 2. Release-please configuration

- [ ] 2.1 Edit `release-please-config.json`: under `packages."."`, add an `extra-files` array with one entry: `{"type": "toml", "path": "uv.lock", "jsonpath": "$.package[?(@.name.value=='cfn-handler')].version"}`
- [ ] 2.2 Verify with `cat release-please-config.json | jq .` that the JSON is valid

## 3. Workflow flip: `--frozen` → `--locked`

- [ ] 3.1 Edit `.github/workflows/ci.yml` line ~68 (`uv sync --frozen --only-group test` → `uv sync --locked --only-group test`); rewrite the inline comment block above the step to describe the new posture
- [ ] 3.2 Edit `.github/workflows/ci.yml` line ~108 (`uv sync --frozen --only-group lint` → `uv sync --locked --only-group lint`)
- [ ] 3.3 Edit `.github/workflows/examples-lint.yml` line ~59 (`uv sync --frozen --only-group lint` → `uv sync --locked --only-group lint`)

## 4. Local environment

- [ ] 4.1 Edit `.envrc` line 26 (`uv sync --all-groups --frozen --quiet` → `uv sync --all-groups --locked --quiet`)
- [ ] 4.2 Rewrite the comment block at `.envrc` lines 17-24 to describe the new posture (release-please syncs `uv.lock`; `--locked` mirrors CI; contributors see lockfile drift locally before push)

## 5. Documentation

- [ ] 5.1 Edit `.github/CONTRIBUTING.md` lines ~152-158: replace the "uv sync --frozen" paragraph with a `--locked` paragraph noting the release-please sync
- [ ] 5.2 Edit `docs/CI.md` lines ~279-298: replace the "Lockfile drift and `--frozen`" subsection with a "Lockfile sync via release-please" subsection
- [ ] 5.3 Edit `docs/CI.md` postmortem at "Root cause #2" (lines ~657-672): append a sentence noting the resolution and back-reference the new section

## 6. Validation (before push)

- [ ] 6.1 `openspec validate release-please-sync-uv-lock --strict` passes
- [ ] 6.2 `uv sync --locked` succeeds locally — proves the catch-up commit cleared all drift
- [ ] 6.3 `just ci-check` passes (no library changes; should be green)
- [ ] 6.4 `git diff main..HEAD --stat` shows: 2 commits, ~7 files changed; no surprising files

## 7. Open PR

- [ ] 7.1 Push the branch `ci/release-please-sync-uv-lock` to origin
- [ ] 7.2 `gh pr create` against `main`. Title: `ci(release): sync uv.lock from release-please and flip CI to --locked`. Body links to the proposal and the three upstream issues (#2561, #2455, #2693)

## 8. Cloud CI on the PR

- [ ] 8.1 `secure-workflows.yml` re-validates SHA-pins; reports SUCCESS (no SHA changes)
- [ ] 8.2 `ci.yml` matrix + lint pass under the new `--locked` install (proves the catch-up worked end-to-end)
- [ ] 8.3 `examples-lint.yml` does not trigger (no examples changes); not required for merge
- [ ] 8.4 `analyze (python)` and `review dependencies` complete

## 9. Merge + first post-merge release

- [ ] 9.1 Squash-merge with title `ci(release): sync uv.lock from release-please and flip CI to --locked`. The `ci:` prefix produces no version bump
- [ ] 9.2 The merge does NOT itself trigger a release. The next `feat:`/`fix:` merge will be the first to exercise the `extra-files` behaviour. Watch that release-please run end-to-end:
  - The release PR diff includes the `uv.lock` self-version line (`cfn-handler` `[[package]]` block, `version = "X.Y.Z"`)
  - Squash-merging the release PR triggers the full downstream pipeline AND the post-merge `ci.yml` on `main` passes under `--locked` (proves the source-of-drift fix is correct)

## 10. Archive

- [ ] 10.1 After step 9.2 confirms in production, run `openspec archive release-please-sync-uv-lock`
- [ ] 10.2 Verify the MODIFIED requirement merges into `openspec/specs/ci-infrastructure/spec.md` correctly (replaces the old `--frozen` requirement)
