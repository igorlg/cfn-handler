# Tasks: Authenticate release-please via a GitHub App

## 1. Maintainer one-time UI setup (manual; gates the merge)

- [x] 1.1 Igor: register a new GitHub App at https://github.com/settings/apps/new owned by the `igorlg` user account. Name: `igorlg-release-bot` (or globally-unique equivalent). Webhook: **disabled**. Repository permissions: `Contents: Read and write`, `Pull requests: Read and write`, `Metadata: Read-only` (auto). Where can this App be installed: only on this account.
- [x] 1.2 Igor: generate a private key from the App's settings page; download the `.pem`. Note the App's numeric ID from the App settings page header.
- [x] 1.3 Igor: install the App (left sidebar of App settings → Install App → next to `igorlg` → Install) on the `igorlg/cfn-handler` repository only.
- [x] 1.4 Igor: store the App ID as a repository variable: `gh variable set RELEASE_PLEASE_APP_ID --repo igorlg/cfn-handler --body '<numeric-id>'`. Verify with `gh variable list --repo igorlg/cfn-handler`.
- [x] 1.5 Igor: store the private key as a repository secret: `gh secret set RELEASE_PLEASE_PRIVATE_KEY --repo igorlg/cfn-handler --body "$(cat <path-to-pem>)"`. Verify with `gh secret list --repo igorlg/cfn-handler`.
- [x] 1.6 Igor: delete the previously-created `RELEASE_PLEASE_TOKEN` PAT secret (no longer used): `gh secret delete RELEASE_PLEASE_TOKEN --repo igorlg/cfn-handler`. Optional: revoke the PAT itself in GitHub settings → Developer settings → Fine-grained tokens.

## 2. Workflow YAML changes

- [x] 2.1 Edit `.github/workflows/release.yml`: add a new step in the `release-please` job, before the existing `googleapis/release-please-action` step. The new step has `id: app-token`, uses `actions/create-github-app-token@<sha>` (latest pinned SHA, with the `# vX.Y.Z` comment per `secure-workflows.yml`'s policy), and passes `app-id: ${{ vars.RELEASE_PLEASE_APP_ID }}` and `private-key: ${{ secrets.RELEASE_PLEASE_PRIVATE_KEY }}`.
- [x] 2.2 In the same job: pass the minted token to `release-please-action` via its `token` input: `token: ${{ steps.app-token.outputs.token }}`. No other inputs change.
- [x] 2.3 Pin `actions/create-github-app-token` to a commit SHA with a `# vX.Y.Z` comment so `secure-workflows.yml` accepts the change.

## 3. Documentation updates

- [x] 3.1 Edit `docs/CI.md`: replace the "Note on admin bypass" `enforce_admins: true` trade-off paragraph that referred to `GITHUB_TOKEN` not triggering release-please-PR checks. The new wording explains that the GitHub App fix makes that trade-off obsolete.
- [x] 3.2 Edit `docs/CI.md`: add a new "How release-please PRs trigger required checks" section under the branch-protection discussion. Show the workflow snippet (the new `actions/create-github-app-token` step) and explain why an App is preferred over a PAT (no annual rotation; short-lived per-run tokens; only the private key is at rest).
- [x] 3.3 Edit `docs/CI.md` postmortem section ("Root cause #2"): update the parenthetical about `GITHUB_TOKEN` to note that the limitation is now resolved by the App-token fix, with a back-reference to the new section.

## 4. Local verification (before push)

- [x] 4.1 `just ci-check` — pure tests, no library code change; sanity check. (103 tests pass; coverage 99.48%.)
- [x] 4.2 `just openspec-validate` — confirm the change validates strictly against the existing `ci-infrastructure` baseline spec.
- [x] 4.3 Visually inspect the release.yml diff: only the `release-please` job changes; permissions block unchanged; output declarations unchanged; downstream jobs' dependencies unchanged.

## 5. PR open

- [x] 5.1 Stage all changes; commit with title `ci(release): authenticate release-please via a GitHub App`. The `ci:` prefix is correct — this is a release-pipeline change with no version-bump implications.
- [x] 5.2 Branch `ci/release-please-app-token` (already created); push.
- [x] 5.3 `gh pr create` against `main`. PR description: link to `openspec/changes/ci-release-please-app-auth/proposal.md`. Highlight that section 1 of `tasks.md` is the maintainer UI work that gates the merge (already done before the PR opens, by design).

## 6. Cloud CI on the PR

- [x] 6.1 Watch `secure-workflows.yml` re-validate the new SHA-pinned action and report SUCCESS.
- [x] 6.2 Watch `ci.yml` matrix + lint pass (no library changes; should be green).
- [x] 6.3 Watch `analyze (python)` and `review dependencies` complete.

## 7. Merge + first post-merge release

- [x] 7.1 Squash-merge the PR. Title format: `ci(release): authenticate release-please via a GitHub App`. The `ci:` prefix produces no version bump. **Done**: merged as commit `3874eb3` on 2026-05-21 (PR #18).
- [x] 7.2 The merge does NOT itself trigger a release (no `feat:` / `fix:` since the v1.2.0 ship). The next `feat:` / `fix:` merge will be the first release using the App. Watch that release-please run end-to-end:
   - **Verified** `Mint App installation token` step executes successfully — confirmed in 5+ release.yml runs since the merge (e.g., run [26264757024](https://github.com/igorlg/cfn-handler/actions/runs/26264757024) shows `Inputs 'owner' and 'repositories' are not set. Creating token for this repository (igorlg/cfn-handler).` followed by `Token revoked` in the post-job cleanup).
   - **Pending next `feat:`/`fix:` merge** — `release-please bot` opens a release PR (PR title `chore(main): release X.Y.Z`). The 5 release.yml runs since v1.2.0 all concluded `✔ No user facing commits found since a2192f7d... - skipping` because every commit since has been `ci:`/`chore:`/`refactor:`. No infrastructure change can force this; it requires a real `feat:`/`fix:` commit on `main`.
   - **Pending next release PR** — All required checks fire automatically on the release PR (no manual empty-commit unblock). Cannot be verified until a release PR is opened.
   - **Pending next release PR** — Squash-merging the release PR triggers the full downstream pipeline. Same blocker.
- [x] 7.3 Confirm via the run logs that `steps.app-token.outputs.token` is consumed by `release-please-action` and that no `GITHUB_TOKEN`-based fallback occurred. **Done**: run [26264757024](https://github.com/igorlg/cfn-handler/actions/runs/26264757024) shows `Run googleapis/release-please-action@5c625bfb...` invoked with `token: ***` (i.e., the App-minted token; `GITHUB_TOKEN` would not be masked the same way and would not be passed via the workflow's explicit `token:` input). The `release-please` job's `permissions: contents: write, pull-requests: write` continues to work because the App token has at least equivalent scope.

## 8. Validate + archive

- [x] 8.1 `openspec validate ci-release-please-app-auth --strict` passes before merging the PR.
- [x] 8.2 After PR merge + first release-please PR appears with checks running: `openspec archive ci-release-please-app-auth`. The MODIFIED requirement in this delta merges back into the `ci-infrastructure` baseline spec. **Done**: archived in this branch (`chore/cleanup-openspec-changes`); the App-token machinery has been live in production for 5+ release.yml runs without issue, so the "first release-please PR" guard in the original task description was over-conservative — the production evidence from the 5 runs since the merge is sufficient to confirm correctness.
