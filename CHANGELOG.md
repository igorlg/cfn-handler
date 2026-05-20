# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This project is maintained automatically with
[release-please](https://github.com/googleapis/release-please) — entries below
v1.0.0 are bot-managed.

## [1.1.0](https://github.com/igorlg/cfn-handler/compare/v1.0.0...v1.1.0) (2026-05-20)


### Features

* initial release (inspired by aws-cloudformation/custom-resource-helper) ([a0184b4](https://github.com/igorlg/cfn-handler/commit/a0184b4dcfd1b5ab8fe73ee7a86b6c734d9b382d))

## [1.0.0] — 2026-05-20

### Added

Initial release of `cfn-handler` — a Python library for writing AWS
CloudFormation Custom Resource lifecycle handlers, inspired by
[`aws-cloudformation/custom-resource-helper`][upstream].

[upstream]: https://github.com/aws-cloudformation/custom-resource-helper

#### Library

- `cfn_handler.CustomResource` class with `create`, `update`, `delete`,
  `poll_create`, `poll_update`, `poll_delete` decorators.
- `cfn_handler.CfnHandlerError` and `cfn_handler.ResponseError` public
  exception hierarchy.
- `__version__` exported, sourced from package metadata.
- Polling state machine for long-running operations (CloudWatch Events
  re-invocation, configurable safety margin against Lambda timeout).
- Reason truncation to CloudFormation's 4096-character limit.
- `LambdaContext` Protocol type for type-safe handler signatures.
- Test mode for unit-testing handlers without sending real responses.
- Zero runtime dependencies (stdlib `urllib`); `boto3` lazily required only
  for polling.

#### Carried-forward fixes from upstream

- **#7** / **#67**: `init_failure` no longer leaks process IDs.
- **#19** / **#36** / **#62**: Documentation tips for common pitfalls.
- **#20** / **#34** / **#39** / **#51**: Polling retry-loop defect resolved.
- **#52** / **#54**: Test mode supported.
- **#66**: `log_level` accepts `int` and `str` consistently.
- **#76**: `LambdaContext` Protocol type for handler signatures.
- **#78**: README polish.

#### Tooling & infrastructure

- Python 3.10–3.14 support, packaged with `hatchling` (PEP 621).
- `uv` for environment + lockfile management.
- `pytest` + `hypothesis` test suite with property-based state-machine tests.
- 95% line + branch coverage enforced in CI.
- `ruff` (lint + format), `mypy` strict, `pyright` strict.
- `just` task runner.
- Nix flake (flake-parts) for reproducible dev shells.
- GitHub Actions: matrix CI (linux/amd64 + arm64 × py3.10–3.14), CodeQL SAST,
  dependency-review on PRs, SHA-pin enforcement on workflow changes.
- Grouped Dependabot weekly.
- Release pipeline: release-please + PyPI Trusted Publishing (no API tokens).
- Examples directory with four SAM-deployable scenarios.
