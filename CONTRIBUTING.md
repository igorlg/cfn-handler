# Contributing to cfn-handler

Thanks for considering a contribution. This project values clear,
testable, well-documented code over cleverness, and tries to keep the
maintenance footprint small.

## Quick start

```sh
git clone git@github.com:igorlg/cfn-handler.git
cd cfn-handler

# Option A: use uv directly
uv sync --all-groups
just test

# Option B: use the Nix dev shell (flake-parts based)
nix develop
uv sync --all-groups
just test
```

## Workflow

1. **Open an issue first** for non-trivial changes. For bug reports,
   include a minimal reproduction. For feature requests, describe the
   use case.
2. **One branch per logical change.** Branch off `main`. Multiple focused
   commits per branch are fine.
3. **Conventional Commits.** Commit messages follow
   [Conventional Commits 1.0.0](https://www.conventionalcommits.org/):
   - `feat:` — new functionality (minor version bump)
   - `fix:` — bug fix (patch version bump)
   - `feat!:` or footer `BREAKING CHANGE:` — major bump
   - `chore:`, `ci:`, `docs:`, `refactor:`, `test:` — no version bump
4. **Run the same checks CI runs.** Don't push code that hasn't passed
   `just lint`, `just typecheck`, `just test-cov`. CI failures should
   surprise no one.
5. **Squash-merge** is the default; the resulting commit message follows
   Conventional Commits and feeds release-please's release notes.

## What counts as a breaking change

Breaking changes require a `feat!:` commit (or `BREAKING CHANGE:` footer)
and bump the major version. Any of the following counts:

- Removing or renaming anything in `cfn_handler.__all__`.
- Tightening type signatures (e.g. removing `Optional`, narrowing a
  parameter type) on public API.
- Changing the shape of CloudFormation responses sent on the wire.
- Raising a different exception type from a documented call.
- Dropping support for a Python version that's still in upstream support
  (Lambda Python runtime support is also a factor).

The following are NOT breaking changes:
- Anything inside `cfn_handler._internal.*`.
- Log line text, formats, or levels.
- Internal exception subclass changes (the public base class staying the
  same is what matters).
- Adding new public API.

## Running checks

`just` is the canonical entry point. The CI runs the same recipes.

```sh
just lint            # ruff check + ruff format --check + cfn-lint over examples
just lint-fix        # ruff check --fix + ruff format
just typecheck       # mypy strict + pyright strict
just test            # pytest, no coverage
just test-cov        # pytest with coverage; fails if <95% line+branch
just build           # uv build wheel + sdist
just test-matrix     # full GH Actions matrix locally via act
```

The `typecheck` recipe runs both mypy and pyright. If they disagree, the
default policy is: prefer mypy, add `# pyright: ignore[<rule>]` with a
short comment, and document the disagreement in the PR description.

## Tests

- Tests live in `tests/` and are plain `def test_*` pytest functions.
  No `unittest.TestCase`.
- Fixtures go in `tests/conftest.py`. JSON event fixtures live in
  `tests/events/*.json` and are loaded by named fixtures.
- New behaviour requires new tests. Bug fixes require a regression test
  that fails on `main` and passes on the fix branch (TDD: write the test
  first).
- `tests/unit/test_state_machine.py` uses `hypothesis` to property-test
  the polling state machine. New polling logic should add rules to that
  state machine, not just example-based tests.
- Coverage gate is **95% line + branch**. We do not accept PRs that
  silently lower coverage. Use `# pragma: no cover` only with a comment
  explaining why a path is impractical to test.

## Type annotations

- All public functions, classes, and methods are fully annotated.
- Use `from __future__ import annotations` only when necessary for
  forward refs; ruff's `UP` ruleset flags unnecessary uses.
- Prefer `collections.abc` over `typing.*` aliases (PEP 585).
- The `_internal/` modules are also typed (mypy strict applies to the
  entire `src/cfn_handler/` tree).

## Logging

The library uses a logger named `cfn_handler` and never adds handlers,
formatters, or filters. Log level is the user's responsibility. Inside
the library, prefer lazy `%s` form:

```python
logger.debug("Sending response to %s", url)   # yes
logger.debug(f"Sending response to {url}")    # no
```

This preserves level deferral and is what ruff's `UP031` allows.

## OpenSpec workflow

Larger changes go through OpenSpec (`openspec/`). Open a change with:

```sh
openspec new change <kebab-case-name>
```

and fill in `proposal.md`, `design.md`, `specs/<capability>/spec.md`,
`tasks.md` before implementing. The slash-commands `/opsx-propose`,
`/opsx-apply`, `/opsx-archive` are wired up if you use OpenCode.

For small fixes a direct PR is fine; for anything that touches the
public API or the spec'd capabilities, use OpenSpec.

## Development environments

- **uv-only.** Install [`uv`](https://github.com/astral-sh/uv) and run
  `uv sync --all-groups`. The Python interpreter is managed by uv.
- **Nix.** `nix develop` enters a shell with python, uv, just, ruff, gh,
  act, and cfn-lint. The flake follows the dendritic / flake-parts
  pattern.

## Lockfile (`uv.lock`)

`uv.lock` is committed and is the source of truth for transitive dependency
versions. After **any** change to `pyproject.toml` dependencies, run
`uv lock` and commit the resulting `uv.lock` in the same PR.

CI installs with `uv sync --frozen` (not `--locked`). This is intentional:
release-please bumps `version` in `pyproject.toml` for releases but cannot
also run `uv lock`, so the local project's version drifts in `uv.lock`
between releases. `--frozen` tolerates that single drift while still
pinning every dependency version to the lockfile. **It does not catch a
contributor forgetting to run `uv lock`** after adding a dep — please do
so manually.

## Reporting security issues

Please do **not** open public issues for security vulnerabilities. Use
GitHub's [private security advisory](https://github.com/igorlg/cfn-handler/security/advisories/new)
form. See [SECURITY.md](SECURITY.md) for details.

## Code of conduct

By participating you agree to abide by the
[Contributor Covenant](CODE_OF_CONDUCT.md).
