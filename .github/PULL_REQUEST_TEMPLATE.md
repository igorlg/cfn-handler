<!--
Thanks for opening a PR!

Title format: Conventional Commits (https://www.conventionalcommits.org/).
  feat: new functionality (minor bump)
  fix: bug fix (patch bump)
  feat!: or `BREAKING CHANGE:` footer for major bumps
  chore/ci/docs/refactor/test: no version bump

The squash-merge commit will use this PR's title as its message; please make
it self-explanatory because release-please will surface it in CHANGELOG.md.
-->

## Issue

<!-- e.g. Closes #123 — link to the issue this PR addresses -->

## Summary

<!-- 2-3 sentences explaining what this PR does and why. -->

## Changes

<!-- Bullet list of concrete changes. -->
-

## Tests

<!-- How did you verify this change?
     - [ ] New tests added for new behaviour
     - [ ] Existing tests still pass (`just test-cov`)
     - [ ] Type-checks pass (`just typecheck`)
     - [ ] Lint passes (`just lint`)
-->

## Breaking changes?

<!--
Yes / No.
If yes, you MUST use `feat!:` or include a `BREAKING CHANGE:` footer in the
PR title / commit message. See CONTRIBUTING.md for what counts as breaking.
-->

## Checklist

- [ ] Conventional Commits prefix in the PR title
- [ ] CHANGELOG entry will be generated automatically by release-please (no manual edit needed)
- [ ] Documentation updated (README / docstrings) if user-facing
- [ ] OpenSpec change opened if this PR modifies a spec'd capability (`openspec/specs/`)
