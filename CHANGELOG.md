# Changelog

## [1.3.0](https://github.com/igorlg/cfn-handler/compare/v1.2.0...v1.3.0) (2026-05-22)


### Features

* **testing:** add cfn_handler.testing module with replay() and helpers ([#24](https://github.com/igorlg/cfn-handler/issues/24)) ([f0f9507](https://github.com/igorlg/cfn-handler/commit/f0f950741e0e95505436e5191e16567131366cdf))

## [1.2.0](https://github.com/igorlg/cfn-handler/compare/v1.1.1...v1.2.0) (2026-05-21)


### Features

* **layer:** publish Lambda Layer to GitHub Releases and ~17 commercial regions ([#15](https://github.com/igorlg/cfn-handler/issues/15)) ([88321d0](https://github.com/igorlg/cfn-handler/commit/88321d0d887660e09878c123d169ed197d06481d))

## [1.1.1](https://github.com/igorlg/cfn-handler/compare/v1.1.0...v1.1.1) (2026-05-21)


### Bug Fixes

* **direnv:** use uv sync --frozen to prevent uv.lock drift on pull ([#11](https://github.com/igorlg/cfn-handler/issues/11)) ([93ab633](https://github.com/igorlg/cfn-handler/commit/93ab63332c628570ba263db1df93db8efef43253))

## [1.1.0](https://github.com/igorlg/cfn-handler/compare/v1.0.0...v1.1.0) (2026-05-21)


### Features

* gha-pre-release recipe, .actrc, and docs/CI.md ([#7](https://github.com/igorlg/cfn-handler/issues/7)) ([7652596](https://github.com/igorlg/cfn-handler/commit/76525962668ad7b724fc3b6f7859521a7aee4363))

## 1.0.0 (2026-05-21)


### Features

* **direnv:** watch pyproject.toml and uv.lock for venv freshness ([3e5d93a](https://github.com/igorlg/cfn-handler/commit/3e5d93a8ffc5306a9fff95c18e44fd3bbdd2d49e))
* initial release (inspired by aws-cloudformation/custom-resource-helper) ([a0184b4](https://github.com/igorlg/cfn-handler/commit/a0184b4dcfd1b5ab8fe73ee7a86b6c734d9b382d))


### Bug Fixes

* **flake:** use python3Packages.cfn-lint and wire up direnv ([2c66f34](https://github.com/igorlg/cfn-handler/commit/2c66f34edaa44737d1ca2253cf0d947a2ef4d9e9))
* **release,ci:** correct pypa SHA + tolerate uv lockfile drift; redo 1.0.0 ([f9ceeeb](https://github.com/igorlg/cfn-handler/commit/f9ceeeb0d22461c7825783c6fdb73787473740b0))

## Changelog

All notable changes to `cfn-handler` are documented here. The format is based
on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

This file is maintained automatically by
[release-please](https://github.com/googleapis/release-please) — entries
below are bot-managed.
