# Spec delta: ci-infrastructure

## MODIFIED Requirements

### Requirement: Lockfile drift policy: release-please syncs `uv.lock`; CI uses `--locked`

Releases SHALL keep the project's self-version entry in `uv.lock`
synchronised with `pyproject.toml`. `release-please-config.json`
SHALL list `uv.lock` as an `extra-files` entry of type `toml`,
matching the project's package via the jsonpath
`$.package[?(@.name.value=='cfn-handler')].version`. The `.value`
accessor descends into release-please's TOML AST node shape (which
exposes string nodes as `{value, kind}` rather than bare strings)
and is required as a workaround for
[googleapis/release-please#2455](https://github.com/googleapis/release-please/issues/2455);
the upstream tracker is
[#2561](https://github.com/googleapis/release-please/issues/2561) and
the proposed fix is PR
[#2693](https://github.com/googleapis/release-please/pull/2693).

CI SHALL install dependencies via `uv sync --locked --only-group <group>`
in `ci.yml` and `examples-lint.yml`. Local development via `.envrc`
SHALL also use `--locked` so contributors see the same diagnostics
locally that CI produces. With release-please syncing `uv.lock`'s
self-version entry, the lockfile and `pyproject.toml` move in
lockstep on every release; with `--locked` enforced, contributors who
edit `pyproject.toml` dependencies without running `uv lock` are
caught immediately by CI rather than discovered at a later
maintenance step.

#### Scenario: Post-release CI on main

- **WHEN** the release PR is merged, bumping `pyproject.toml` from
  `X.Y.Z` to `X.Y.Z+1` *and* the corresponding `[[package]] name =
  "cfn-handler"` `version` in `uv.lock` (because the `extra-files`
  entry directs release-please to update both)
- **THEN** the next `ci.yml` run on `main` succeeds because `uv sync
  --locked` finds `pyproject.toml` and `uv.lock` consistent

#### Scenario: A contributor adds a new runtime dependency without re-locking

- **WHEN** a PR adds a dependency to `pyproject.toml` but does not
  include the resulting `uv.lock` change
- **THEN** `uv sync --locked` fails the PR's CI run with
  `The lockfile at uv.lock needs to be updated, but --locked was
  provided`, surfacing the missed re-lock before review

#### Scenario: release-please's TOML AST shape regresses upstream

- **WHEN** a future release-please bump changes the parser such that
  the `.value` accessor no longer matches the cfn-handler package
- **THEN** the next release PR ships with `uv.lock`'s self-version
  unchanged; the post-merge `ci.yml` run on `main` fails under
  `--locked` and the failure is loud, fast, and bisectable to the
  release PR commit
