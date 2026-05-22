# release-please `uv.lock` updater validator

A local, network-free check that release-please's `extra-files`
configuration in [`release-please-config.json`](../../release-please-config.json)
will surgically update `uv.lock`'s `cfn-handler` self-version entry —
and only that entry — on every release.

## Why this exists

Release-please's `GenericToml` updater is configured via a jsonpath that
must navigate release-please's internal TOML AST (where string nodes are
exposed as `{value, kind}` objects, not bare strings). The bare form
`$.package[?(@.name=='cfn-handler')].version` does NOT match — see
[googleapis/release-please#2455][issue-2455]. The working form needs
`.value`:

```
$.package[?(@.name.value=='cfn-handler')].version
```

[Upstream PR #2693][pr-2693] proposes to make the bare form work; until
it lands, the `.value` workaround is what we have.

The class-level docstring on `GenericToml` says:

> Note that used parser does reformat the document and removes all
> comments, and converts everything to pure TOML.

That is misleading. The actual implementation in `util/toml-edit.js`
uses a `TaggedTOMLParser` that annotates each value with byte offsets;
the replacement is a surgical `input.slice(0, start) + new + input.slice(end)`.
Original formatting, comments, and ordering survive. If the docstring
had been right, this whole approach would be unusable (1872-line
`uv.lock` rewrites every release). It isn't — but **trust but verify**;
this script keeps that verification automated.

[issue-2455]: https://github.com/googleapis/release-please/issues/2455
[issue-2561]: https://github.com/googleapis/release-please/issues/2561
[pr-2693]: https://github.com/googleapis/release-please/pull/2693

## What the script checks

| # | Check | Failure mode it catches |
|---|---|---|
| 1 | Configured jsonpath matches the cfn-handler entry | Someone broke / removed the `extra-files` block; `uv.lock` will go un-updated |
| 2 | The line count of `uv.lock` is preserved | release-please started re-serialising the file (whole-file rewrite) |
| 3 | Exactly one line changed | The jsonpath now matches more than the cfn-handler self-entry |
| 4 | The changed line is `version = "X.Y.Z"` | The matched node isn't a version field |
| 5 | Byte delta is small and explainable | Something larger than the version string changed |
| 6 | Bare `@.name` jsonpath does NOT match | Bug #2455 is fixed upstream; we can drop `.value` and simplify the config |

## How to run

```sh
cd tests/release-please
npm install        # one-time, after a fresh clone or version bump
node validate-uv-lock-updater.js
```

Or via the npm script:

```sh
npm run validate
```

`npm install` is committed-lockfile reproducible (`package-lock.json` is
checked in). `node_modules/` is gitignored.

A `just` recipe will be added later to wire this in as a pre-push check;
until then it's manual.

## Version pinning policy

`package.json` pins `release-please` to **the exact version bundled in
the `release-please-action` SHA used by `.github/workflows/release.yml`**.

When you bump `googleapis/release-please-action` in `release.yml`:

1. Find the new action's bundled release-please version. The action's
   `package.json` declares it; e.g. action v4.4.1's `package.json`
   pinned `release-please` to `^17.1.3` and shipped with `17.3.0` in
   the action's `package-lock.json`.
2. Update `devDependencies.release-please` here to match.
3. Re-run `npm install`; commit the updated `package-lock.json`.
4. Re-run this validator. If anything in the output changes (especially
   the negative test going from FAIL→PASS, suggesting #2693 has
   landed), update [the spec][spec] and the inline workaround comments
   in `release-please-config.json`.

[spec]: ../../openspec/specs/ci-infrastructure/spec.md

## What this script does NOT validate

- Whether release-please will *open the right release PR* (commit
  parsing, version bumping logic). That's tested by release-please's
  own test suite.
- The full release pipeline. For end-to-end validation, the cheap
  signal is "merge a `feat:` or `fix:`, watch the release PR's diff
  contain the `uv.lock` self-version line".
- That `uv sync --locked` actually succeeds in CI under the new posture.
  That's verified by `just ci-check` in this repo.
