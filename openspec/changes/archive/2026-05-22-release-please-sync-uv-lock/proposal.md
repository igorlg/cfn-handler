# Proposal: Sync `uv.lock` self-version via release-please; flip CI back to `--locked`

## Why

After every release-please merge, `pyproject.toml`'s `version` is bumped
but the corresponding `[[package]] name = "cfn-handler"` entry in
`uv.lock` is left at the old version. This drift surfaces locally on
every `git pull` followed by `uv sync` (the working tree shows
`uv.lock` modified) and has historically broken CI. The accepted
workaround was to install via `uv sync --frozen` everywhere — in
`ci.yml`, `examples-lint.yml`, and `.envrc` — which tolerates that
drift but accepts a known foot-gun in return: a contributor adding a
runtime dependency to `pyproject.toml` without running `uv lock` is
not caught by CI.

A community-discovered fix to `release-please-config.json`
([googleapis/release-please#2561][issue-2561]; comment thread on
[#2455][issue-2455]) lets release-please update `uv.lock`'s self-
version entry alongside `pyproject.toml` via the existing
`extra-files` mechanism. The trick is the jsonpath syntax
`$.package[?(@.name.value=='<pkg>')].version` — the `.value` accessor
descends into release-please's internal TOML AST node shape (where
strings are exposed as `{value, kind}` rather than bare strings),
working around the bug tracked in #2455. Upstream PR
[#2693][pr-2693] aims to make this `.value` accessor unnecessary by
fixing the parser; until that ships, the workaround is stable.

With both files now bumped together, the original justification for
`--frozen` evaporates. We can flip CI and `.envrc` back to `--locked`
and close the contributor-relock foot-gun in the same change.

[issue-2561]: https://github.com/googleapis/release-please/issues/2561
[issue-2455]: https://github.com/googleapis/release-please/issues/2455
[pr-2693]: https://github.com/googleapis/release-please/pull/2693

## What Changes

### Release pipeline configuration

- **MODIFIED** `release-please-config.json` — add an `extra-files`
  entry under `packages."."` that targets `uv.lock` with the
  TOML-jsonpath workaround. Release-please will rewrite the matched
  `version` field in lockstep with `pyproject.toml` on every release
  PR.

### CI workflows

- **MODIFIED** `.github/workflows/ci.yml` — both `uv sync --frozen`
  invocations (test job, lint job) become `--locked`. The inline
  comment explaining the `--frozen` choice is rewritten to describe
  the new posture.
- **MODIFIED** `.github/workflows/examples-lint.yml` — `uv sync
  --frozen --only-group lint` becomes `--locked`.

### Local developer environment

- **MODIFIED** `.envrc` — `uv sync --all-groups --frozen --quiet`
  becomes `--locked`. The block comment is rewritten: with
  release-please now syncing `uv.lock`, the original drift footgun is
  fixed at the source; `--locked` here mirrors CI and gives developers
  the same diagnostic immediately.

### One-shot lockfile catch-up

- **MODIFIED** `uv.lock` — a separate commit on this branch (landing
  *before* the substantive change) re-locks to bring the self-version
  entry from `1.1.1` to `1.2.0`. Without this, the very PR that flips
  CI to `--locked` would fail its own CI run. The diff is exactly one
  line.

### Documentation

- **MODIFIED** `.github/CONTRIBUTING.md` — the "Lockfile (`uv.lock`)"
  section's `--frozen` paragraph is replaced with a `--locked`
  rationale.
- **MODIFIED** `docs/CI.md` — the "Lockfile drift and `--frozen`"
  subsection is replaced with a "Lockfile sync via release-please"
  subsection. The postmortem at "Root cause #2: `--locked` vs
  release-please version bump" gains a forward-reference noting the
  resolution.

### Non-goals

- **No** library API changes. This is purely CI/release tooling.
- **No** changes to PyPI Trusted Publishing, OIDC, branch protection,
  or any other auth path.
- **No** preemptive update of `secure-workflows.yml` policy or
  Dependabot grouping. The `--locked` flip may surface Dependabot PRs
  that fail because the bot can't re-lock; if it does, that becomes a
  separate change. We expect Dependabot's pip ecosystem to re-lock
  correctly because it already runs `uv lock` on dependency bumps.

## Capabilities

### Modified Capabilities

- `ci-infrastructure` — replaces the existing
  `Lockfile drift policy: uv sync --frozen in CI; manual uv lock
  after dependency edits` requirement with a new
  `Lockfile drift policy: release-please syncs uv.lock; CI uses
  --locked` requirement. The behavioural contract changes: CI now
  catches a contributor adding a dep without re-locking; release PRs
  now include the matching `uv.lock` self-version bump.

## Impact

- **Maintainer workload**: zero recurring; one-time edit to
  `release-please-config.json` plus the workflow / docs cleanup.
- **Release pipeline**: every release PR henceforth includes the
  `uv.lock` self-version line in its diff. No manual intervention.
- **Contributor workflow**: `uv sync` (default `--locked` semantics
  via `.envrc`) now catches missed re-locks immediately rather than
  silently producing a stale lockfile. Same applies to CI.
- **Backwards compatibility**: nothing user-facing breaks. The first
  release-please PR opened after this lands will be the first to
  ship the `extra-files` behaviour; an unlikely failure (e.g., the
  `.value` accessor regresses upstream) would surface as a
  release-please PR with `uv.lock` unchanged, caught by the next
  post-merge CI run on `main`.
- **Risk**: the `.value` jsonpath syntax is undocumented (it leaks
  release-please's TOML AST shape). Pinned action SHA insulates us
  from upstream surprises; if PR #2693 ships and we bump the action,
  the bare jsonpath becomes the official form and we'd update in a
  follow-up change.
