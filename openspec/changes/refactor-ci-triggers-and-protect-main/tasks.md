# Tasks: Refactor CI triggers and protect main

## 1. Workflow YAML changes

- [x] 1.1 Edit `.github/workflows/ci.yml`: remove the `push: branches: [main]` trigger from the `on:` section. Keep `pull_request: branches: [main]`.
- [x] 1.2 Edit `.github/workflows/ci.yml`: remove the `cfn-lint over examples` step from the `lint` job (the last step, `uv run cfn-lint examples/**/template.yaml`).
- [x] 1.3 Edit `.github/workflows/ci.yml`: add a new job named `ci-pass` at the end (after `lint`). Job: `name: CI passed`, `if: always()`, `needs: [test, lint]`, single shell step that loops over `${{ needs.test.result }}` and `${{ needs.lint.result }}`, exiting non-zero if either is not `success` or `skipped`.
- [x] 1.4 Create `.github/workflows/examples-lint.yml`: PR-only trigger (`pull_request: branches: [main]`), `paths: ['examples/**', '.github/workflows/examples-lint.yml']`, top-level `permissions: contents: read`, single job `cfn-lint` on `ubuntu-24.04` that checks out, sets up uv (cache-suffix `examples-lint`), runs `uv sync --frozen --only-group lint` and `uv run cfn-lint examples/**/template.yaml`. SHA-pin every action with version comments.
- [x] 1.5 Edit `.github/workflows/secure-workflows.yml`: remove the `push: branches: [main]` (with paths) trigger. Keep `pull_request: branches: [main]` with `paths: ['.github/workflows/**']`.

## 2. Justfile

- [x] 2.1 Edit `gha-pre-release` recipe in `justfile`: insert a step `3a` between the existing step 3 (test-matrix) and step 4 (codeql), invoking `act push -W .github/workflows/examples-lint.yml --container-architecture linux/amd64 --secret GITHUB_TOKEN="$(gh auth token)" --action-cache-path /tmp/act-cache-examples-lint`. Update the recipe doc-comment header to mention `examples-lint.yml` in the steps list.

## 3. Docs

- [x] 3.1 Update `docs/CI.md` "Workflow inventory" section: split the old `cfn-lint` row into its own `examples-lint.yml` entry; flag it as informational (not required for merge).
- [x] 3.2 Update `docs/CI.md` "Triggers and concurrency" section: document the new PR-only model for `ci.yml` and `secure-workflows.yml`; explain why CodeQL stays dual-triggered.
- [x] 3.3 Update `docs/CI.md` "Branch protection" section: remove the "currently disabled" note; document the active configuration (required checks list, admin bypass, linear history); include the `gh api -X PUT` JSON command as the reproducible recipe.
- [x] 3.4 Update `docs/CI.md` "Adding a new workflow" checklist: add an item "if you add a job to `ci.yml`, also add it to `ci-pass`'s `needs:` list".

## 4. Local verification (before push)

- [x] 4.1 Run `just ci-check` — pure tests, no workflow changes affect this; sanity check.
- [x] 4.2 Run `just gha-pre-release` — exercises every changed workflow under `act`. Expect green.
- [x] 4.3 Inspect each workflow file diff one last time: `gh secret list` (no inadvertent secret access), permission scopes, SHA-pinned actions still pinned.

## 5. PR open + cloud CI

- [ ] 5.1 Stage all changes; commit with message `refactor(ci): PR-only triggers + ci-pass aggregator + examples-lint split`.
- [ ] 5.2 Create branch `feat/ci-trigger-refactor` (or similar); push.
- [ ] 5.3 `gh pr create` against `main`. PR description references this OpenSpec change directory.
- [ ] 5.4 Watch cloud CI: `CI passed` should appear for the first time; `analyze (python)`, `review dependencies`, `ensure SHA-pinned actions` should also run. Verify all green.
- [ ] 5.5 If `CI passed` reports failure, debug and push fixes before proceeding to step 6.

## 6. Enable branch protection (irreversible-ish step)

- [ ] 6.1 Once cloud CI is green and a `CI passed` check has appeared at least once on a `main` history (so GitHub knows the check name): `gh api -X PUT /repos/igorlg/cfn-handler/branches/main/protection --input <protection.json>` with the JSON: `required_status_checks.contexts = ["CI passed", "analyze (python)", "review dependencies", "ensure SHA-pinned actions"]`, `strict: true`, `enforce_admins: false`, `required_pull_request_reviews: null`, `restrictions: null`, `required_linear_history: true`, `allow_force_pushes: false`, `allow_deletions: false`, `block_creations: false`, `required_conversation_resolution: false`.
- [ ] 6.2 Verify `gh api /repos/igorlg/cfn-handler/branches/main/protection` returns the configured rule (no longer 404).
- [ ] 6.3 Verify in the GitHub UI: Settings → Branches → main rule shows the four required checks.

## 7. Merge

- [ ] 7.1 Squash-merge the PR. Title format: `refactor(ci): PR-only triggers + ci-pass aggregator + examples-lint split (#N)`.
- [ ] 7.2 Verify post-merge: `release.yml` runs (release-please evaluates; no release because chore commit); `ci.yml` does NOT run on the merge commit (PR-only now). The CodeQL run on `main` is expected (still dual-triggered).
- [ ] 7.3 Verify branch protection works: from a fresh terminal, `git checkout main && git commit --allow-empty -m "ci: prove protection works" && git push origin main` should be rejected with a branch-protection-rule-violation error. Reset locally if needed: `git reset --hard origin/main`.

## 8. Validate + archive

- [x] 8.1 `openspec validate refactor-ci-triggers-and-protect-main --strict` should pass before merge.
- [ ] 8.2 After PR is merged: `openspec archive refactor-ci-triggers-and-protect-main`. The MODIFIED requirements merge into `openspec/specs/ci-infrastructure/spec.md`.
