# Spec delta: ci-infrastructure

## MODIFIED Requirements

### Requirement: Release pipeline driven by Conventional Commits and Trusted Publishing

Releases SHALL be driven entirely by Conventional Commits parsed by `release-please-action`. Merging the auto-generated release PR with the title `chore(main): release X.Y.Z` SHALL trigger a chain of jobs in `release.yml` that: tag `vX.Y.Z`; build wheel and sdist; upload artifacts to a GitHub Release; and publish to PyPI via OIDC Trusted Publishing in the `pypi` environment. The Trusted Publisher binding SHALL be parameterised by repository, workflow filename (`release.yml`), and environment name (`pypi`); no PyPI API token is held anywhere.

`release-please-action` SHALL authenticate using a short-lived installation token minted from a dedicated GitHub App (registered to the repository owner, installed only on this repository, granted exactly `Contents: write` and `Pull requests: write` permissions), NOT the default `GITHUB_TOKEN`. The minting step SHALL run before `release-please-action` and pass the resulting token via the action's `token` input. This requirement exists because GitHub blocks PRs opened with the default `GITHUB_TOKEN` from triggering downstream workflow runs (anti-recursion); without an App-minted token, required status checks on the release PR never fire and the PR cannot be merged. The App's numeric ID SHALL be stored as a repository **variable** (`vars.RELEASE_PLEASE_APP_ID`, non-sensitive); its private key SHALL be stored as a repository **secret** (`secrets.RELEASE_PLEASE_PRIVATE_KEY`).

#### Scenario: A `feat:` commit lands on main
- **WHEN** a contributor merges a PR with title `feat: <description>` to `main`
- **THEN** `release-please-action` opens (or updates) a release PR proposing a minor version bump

#### Scenario: The release PR is merged
- **WHEN** the release PR is squash-merged
- **THEN** `release.yml` runs `release-please-action`, sees `release_created=true`, builds artifacts, uploads to GitHub Release, and the `publish-pypi` job authenticates via OIDC and uploads the artifacts to PyPI

#### Scenario: PyPI Trusted Publisher is misconfigured
- **WHEN** the publisher binding does not match (wrong workflow filename, wrong environment, wrong repo)
- **THEN** `pypa/gh-action-pypi-publish` fails the OIDC exchange and the publish step errors with a 403 from PyPI; the wheel/sdist artifacts on the GitHub Release are unaffected

#### Scenario: Release PR opened with the App's token triggers required checks
- **WHEN** `release-please-action` opens or updates a release PR using the GitHub App installation token
- **THEN** the four required status checks on `main`'s branch protection (`CI passed`, `analyze (python)`, `review dependencies`, `ensure SHA-pinned actions`) all run automatically against the release PR's head, with no manual unblocks needed

#### Scenario: App credential is missing or invalid
- **WHEN** `vars.RELEASE_PLEASE_APP_ID` is unset, or `secrets.RELEASE_PLEASE_PRIVATE_KEY` is missing or expired
- **THEN** the `Mint App installation token` step fails before `release-please-action` runs; the release pipeline halts loudly rather than silently falling back to `GITHUB_TOKEN` (which would produce non-triggering PRs)
