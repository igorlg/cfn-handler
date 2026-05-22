# Proposal: Authenticate release-please via a GitHub App

## Why

`release.yml`'s `release-please` job currently uses the default
`GITHUB_TOKEN` to push the release branch and open the release PR.
GitHub deliberately blocks the default `GITHUB_TOKEN` from creating
follow-up workflow runs (anti-recursion). The consequence: PRs opened
by `release-please-action` never have `pull_request` workflows fire
against them, so every required status check on `main`'s branch
protection (`CI passed`, `analyze (python)`, `review dependencies`,
`ensure SHA-pinned actions`) sits at "Expected — Waiting for status to
be reported", unmergeable without a manual unblock.

This first surfaced when we shipped v1.2.0 (the Lambda Layer feature
release): the maintainer had to push an empty commit to the
release-please branch from a real account before any check could run.
That works once but it's not a sustainable release process.

Two repair paths exist:

1. **Personal Access Token (PAT)** — fine-grained PAT with
   `Contents: write` + `Pull requests: write`, stored as a repo
   secret, passed to `release-please-action` via its `token` input.
   PRs opened with a PAT trigger workflows normally. Cost: max 1-year
   expiry, manual rotation each year.
2. **GitHub App** — a dedicated App registered to the maintainer,
   installed on `igorlg/cfn-handler` only, granted exactly
   `Contents: write` + `Pull requests: write`. The workflow mints a
   short-lived (~1h) installation token on every run via
   `actions/create-github-app-token@<sha>`; tokens trigger workflows
   normally. Cost: ~10 extra minutes upfront, two repo state items
   instead of one (App ID + private key); zero ongoing rotation.

The App approach wins after year 1 in the steady state and aligns with
the pattern used by AWS Powertools, AWS CDK, and other serious OSS
Python libraries. It also keeps the long-lived credential (the App's
private key) out of any individual workflow-run context — only
short-lived installation tokens appear in run logs.

## What Changes

### Workflow

- **MODIFIED** `.github/workflows/release.yml` — the `release-please`
  job gains a preceding step that mints an installation token via
  `actions/create-github-app-token@<sha>`. `release-please-action`
  consumes the minted token through its `token` input instead of the
  implicit `GITHUB_TOKEN`. No other jobs change.

### Repository state

- **NEW** `vars.RELEASE_PLEASE_APP_ID` — the numeric App ID,
  non-sensitive, stored as a repository **variable** (not secret).
- **NEW** `secrets.RELEASE_PLEASE_PRIVATE_KEY` — the PEM private key,
  the only long-lived credential at rest.
- **NEW** GitHub App `igorlg-release-bot` (or similar) — owned by
  `igorlg`, installed only on `igorlg/cfn-handler`, granted exactly
  `Contents: Read and write` and `Pull requests: Read and write`.

### Documentation

- **MODIFIED** `docs/CI.md` — replace the existing "known trade-off"
  note about `GITHUB_TOKEN` not triggering release-please-PR checks
  with a new "How release-please PRs trigger required checks" section
  that documents the App registration, the workflow snippet, and the
  rationale for choosing App over PAT.

### Out of scope

- **No** API or library code changes. This is purely a CI/release-
  pipeline auth migration.
- **No** change to PyPI Trusted Publishing, OIDC into AWS, or any
  other authentication path. Those remain as specified in the existing
  `ci-infrastructure` baseline.
- **No** change to branch protection (`enforce_admins`, required
  checks, linear-history) — same posture; the App fix means the
  required checks now actually fire on release-please PRs without
  manual unblocks.

## Capabilities

### Modified Capabilities

- `ci-infrastructure` — adds a new sub-requirement under the existing
  "Release pipeline driven by Conventional Commits and Trusted
  Publishing" requirement specifying the auth mechanism for
  `release-please-action`.

## Impact

- **Maintainer workload**: ~15 minutes one-time UI setup; zero
  recurring rotation.
- **Release pipeline**: every release-please PR now arrives with all
  required checks running, no manual empty-commit unblocks.
- **Security posture**: the App's private key is the only long-lived
  credential; minted tokens are short-lived and scoped to the install.
  Compared to a PAT, no annual expiry / rotation chore.
- **User-facing**: none. Library API and Layer publishing unchanged.
- **Backward compatibility**: nothing to break — this is the first
  release-please run since v1.2.0; the App auth replaces the default
  `GITHUB_TOKEN` for all future runs.
