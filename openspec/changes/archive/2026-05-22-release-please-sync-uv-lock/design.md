# Design: Sync `uv.lock` self-version via release-please; flip CI back to `--locked`

## Context

Two related drifts have lived with this project since v1.0.0:

1. **Release-time drift.** `release-please-action` knows about
   `pyproject.toml` (via its `release-type: python`) and bumps the
   `version` field on every release PR. It does *not* know about
   `uv.lock`. Consequence: every release-please merge produces a main
   commit where `pyproject.toml.version` is the new version but
   `uv.lock` still records the old self-version. Local `uv sync`
   silently rewrites `uv.lock` to match, leaving a dirty working tree
   the developer didn't ask for.

2. **Contributor drift.** A contributor editing `pyproject.toml`
   dependencies but forgetting `uv lock` produces a stale lockfile
   that ships in their PR. Documented in CONTRIBUTING.md as a
   tradeoff but not enforced.

CI was historically configured with `uv sync --frozen` to tolerate
drift #1 (the release-time case). `--frozen` does not validate
`pyproject.toml` ↔ `uv.lock` consistency; it just installs from the
lockfile as-is. The cost was that drift #2 also went uncaught.

A community fix to `release-please-config.json`
([googleapis/release-please#2561][issue-2561]; the working syntax
discovered in [#2455][issue-2455]) closes drift #1 by making
release-please update the lockfile's self-version entry alongside
`pyproject.toml`. With drift #1 closed, `--frozen` is no longer
load-bearing, and we can flip back to `--locked` to also close drift
#2.

[issue-2561]: https://github.com/googleapis/release-please/issues/2561
[issue-2455]: https://github.com/googleapis/release-please/issues/2455
[pr-2693]: https://github.com/googleapis/release-please/pull/2693

## Goals / Non-Goals

**Goals:**

- Eliminate the post-release-PR `uv.lock` drift on every developer's
  workstation.
- Catch missing `uv lock` re-locks in CI rather than at later
  maintenance points.
- Keep the change scoped to release tooling + CI configuration. No
  library, API, or behaviour changes.

**Non-Goals:**

- Wait for the upstream "proper" fix (release-please PR
  [#2693][pr-2693]). The `.value` workaround is stable enough today;
  bumping the action when #2693 lands is a future follow-up.
- Re-engineer Dependabot grouping. Pip ecosystem already runs
  `uv lock` on dependency bumps; if it surprises us, that's a
  separate change.
- Touch PyPI Trusted Publishing, OIDC, branch protection, or any
  other auth path.

## Decisions

### D1. Use release-please's `extra-files` mechanism with a TOML jsonpath

The fix is a single `extra-files` block in
`release-please-config.json`:

```json
"extra-files": [
  {
    "type": "toml",
    "path": "uv.lock",
    "jsonpath": "$.package[?(@.name.value=='cfn-handler')].version"
  }
]
```

The jsonpath uses `@.name.value` rather than `@.name`. Release-
please's TOML parser exposes string nodes as `{value, kind}`
objects rather than bare strings; the `.value` accessor descends
into the AST node. Tracked upstream as bug #2455; the upstream
fix (#2693) would make `@.name=='cfn-handler'` work, at which
point the bare form becomes the documented one.

**Rejected alternative — post-release-PR commit pushing `uv lock`
back to the release branch.** A separate workflow could detect
release-please's commit, run `uv lock`, and push the result. This
would work but requires either (a) granting bot-write access to a
side-channel workflow or (b) Igor running the merge with elevated
auth. It also moves the bump out of release-please's atomic PR,
making release rollbacks more complex (two commits to revert
instead of one).

**Rejected alternative — switch to a release tool that natively
understands `uv.lock`.** None exist that match release-please's
feature set (Conventional-Commits-driven SemVer, GitHub-native PR
flow, manifest mode, multi-file updates). Build-vs-buy is squarely
buy here.

### D2. Flip CI and `.envrc` to `--locked` in the same change

Once D1 closes drift #1, the rationale for `--frozen` evaporates:
both files now move together on every release. We could keep
`--frozen` defensively, but the net effect is to keep drift #2 (the
contributor case) as a foot-gun for no benefit. The principled
move is to flip to `--locked` and let CI catch the drift it was
designed to catch.

**Rejected alternative — keep `--frozen` for now, flip later.** The
risk of waiting is institutional memory: someone reading the
`--frozen` rationale comment in `ci.yml` six months from now would
see "release-please can't bump uv.lock" and have no signal that the
problem is fixed. Flipping now is a single commit; waiting is a
permanent stale comment unless we also rewrite the comment. If we're
already rewriting the comment, we should make the rationale
self-consistent.

### D3. Catch-up `uv lock` lands as a separate first commit on this branch

The current `main` has `uv.lock` at v1.1.1, `pyproject.toml` at
v1.2.0. If we flip to `--locked` without first re-locking, the very
first CI run on this branch fails with `The lockfile at uv.lock
needs to be updated, but --locked was provided`. Two options:

- (a) Combined commit: include the one-line `uv.lock` bump in the
  same commit as the workflow flip.
- (b) Separate commit: re-lock first, then flip.

We chose (b). The `uv.lock` self-version diff (1.1.1 → 1.2.0) is a
mechanical sync, not a substantive change; isolating it makes the
PR's substantive diff self-contained and reviewable. Squash-merge
collapses both into a single `ci(release):` commit on `main` so
the historical record stays clean.

### D4. Update `.envrc` to mirror CI

The `.envrc` block currently runs `uv sync --all-groups --frozen`
explicitly to avoid surprising contributors with a dirty `uv.lock`
on `git pull`. With drift #1 closed, the surprise no longer occurs;
keeping `--frozen` would diverge from CI's posture and let
contributors land PRs that fail CI for a reason their local shell
can't reproduce. Match CI: `--locked` everywhere.

### D5. Documentation: rewrite the "why `--frozen`" notes, don't delete them

Three places explain the historical `--frozen` choice:
`.github/CONTRIBUTING.md`, `docs/CI.md`, `.envrc`'s inline comment,
and `ci.yml`'s inline comment. We rewrite each to describe the new
posture (release-please syncs `uv.lock`; CI uses `--locked`) rather
than deleting the section, because future readers will want to know
both *that* the lockfile is kept in sync and *how*. The CI.md
postmortem at "Root cause #2" stays as historical context with a
forward-reference to the new section.

## Risks / Trade-offs

- **Risk: `.value` jsonpath is undocumented.** → Mitigation: action
  is SHA-pinned (`5c625bfb...`), so a future upstream change cannot
  silently break us. Spec scenario explicitly covers regression
  detection: `--locked` CI fails the next post-merge run on `main`,
  surfacing the issue immediately. Comment in
  `release-please-config.json` references the upstream issues so a
  future-Igor doesn't reverse-engineer the syntax.
- **Risk: existing drift on `main` (1.1.1 vs 1.2.0) breaks `--locked`
  on this very PR.** → Mitigation: D3's separate catch-up commit.
- **Risk: Dependabot pip PRs fail under `--locked` if it forgets to
  re-lock.** → Tested behaviour: Dependabot's `pip` ecosystem runs
  the underlying lock update on bumps. If a Dependabot PR ever lands
  with a stale lockfile, CI catches it (the desired behaviour) and
  we open a follow-up to fix the bot config.
- **Trade-off: tighter coupling between release-please's internal
  TOML AST and our config.** → Accepted because the alternative
  (out-of-band `uv lock` push) is more complex and more fragile.
  Coupling is documented; SHA pin guards against silent breakage.
