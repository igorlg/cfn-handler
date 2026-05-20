# Tasks: Bootstrap cfn-handler v1.0.0

## 1. Repo skeleton

- [ ] 1.1 Create `.gitignore` covering Python (`__pycache__`, `*.egg-info`, `.venv`, `dist/`, `build/`), tooling (`.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `htmlcov`, `.coverage*`), Nix (`result`, `result-*`), editor (`.idea`, `.vscode`, `*.swp`).
- [ ] 1.2 Create `LICENSE` (Apache-2.0) with dual copyright header: original Amazon copyright + new "Copyright 2026 Igor Lopes Gomes" line.
- [ ] 1.3 Create `NOTICE` file referencing the upstream attribution per Apache-2.0 §4.
- [ ] 1.4 Create `README.md` introducing the project, quickstart code, comparison to `crhelper`, link to archived fork, badges (CI, PyPI, license, py-versions).
- [ ] 1.5 Create `CHANGELOG.md` with v1.0.0 stub entry (release-please will manage future entries).
- [ ] 1.6 Create `CONTRIBUTING.md` documenting: branch-per-PR, conventional commits, what counts as a breaking change, how to run checks (`just lint`, `just test`, `just typecheck`), the dual mypy+pyright policy.
- [ ] 1.7 Create `SECURITY.md` pointing at GitHub security advisories as the disclosure channel.
- [ ] 1.8 Create `CODE_OF_CONDUCT.md` (standard Contributor Covenant 2.1).

## 2. pyproject.toml + lockfile

- [ ] 2.1 Write `pyproject.toml` with `[build-system] hatchling`, PEP 621 `[project]` table (name=cfn-handler, version="1.0.0", license="Apache-2.0", requires-python=">=3.10", classifiers including Typed and 3.10–3.14, keywords, URLs).
- [ ] 2.2 Configure `[tool.hatch.build.targets.wheel] packages = ["src/cfn_handler"]` and ensure `py.typed` ships.
- [ ] 2.3 Configure `[dependency-groups]` (PEP 735): `test` (pytest, pytest-cov, hypothesis, moto[cloudformation]), `lint` (ruff, mypy, pyright), `dev` (composes test+lint).
- [ ] 2.4 Configure `[tool.ruff]` with line-length=120, target=py310, select rule families (E,F,W,I,UP,B,C4,SIM,RUF,PTH,TID,PT,PYI,TC,ANN,D), per-file-ignores for tests/examples/_internal, pydocstyle convention=google.
- [ ] 2.5 Configure `[tool.mypy]` strict=true, files=["src/cfn_handler"], python_version=3.10.
- [ ] 2.6 Configure `[tool.pyright]` typeCheckingMode=strict, include=["src/cfn_handler"], pythonVersion=3.10.
- [ ] 2.7 Configure `[tool.pytest.ini_options]` with strict markers, testpaths=["tests"], addopts=`-ra --strict-markers --strict-config`, integration marker registered.
- [ ] 2.8 Configure `[tool.coverage.run] branch=true source=["src/cfn_handler"]` and `[tool.coverage.report] fail_under=95`.
- [ ] 2.9 Run `uv lock` to generate `uv.lock` and verify `uv sync --all-groups` succeeds.

## 3. Source code

- [ ] 3.1 Create `src/cfn_handler/__init__.py` re-exporting `CustomResource`, `CfnHandlerError`, `ResponseError`, and `__version__` (sourced via `importlib.metadata.version(__package__)`); declare explicit `__all__`.
- [ ] 3.2 Create `src/cfn_handler/py.typed` (empty file, PEP 561 marker).
- [ ] 3.3 Create `src/cfn_handler/exceptions.py` defining `CfnHandlerError(Exception)` and `ResponseError(CfnHandlerError)` with full type annotations and docstrings.
- [ ] 3.4 Create `src/cfn_handler/_internal/__init__.py` (empty; subpackage marker).
- [ ] 3.5 Create `src/cfn_handler/_internal/log.py` providing the named logger `cfn_handler` (no handlers attached; respects user log config).
- [ ] 3.6 Create `src/cfn_handler/_internal/response.py` implementing `build_response()` (constructs the JSON payload per CFN spec, including `PhysicalResourceId`, `Reason` truncation to 4096 chars with ellipsis) and `send_response()` (HTTP PUT via `urllib.request` with `Content-Type: ""`, raising `ResponseError` chained from any underlying exception).
- [ ] 3.7 Create `src/cfn_handler/_internal/timing.py` with `time_remaining_ms(context)` helper and the safety-margin decision (default 30s).
- [ ] 3.8 Create `src/cfn_handler/_internal/poller.py` implementing CloudWatch Events rule provisioning, target wiring, and teardown via lazy-imported `boto3`; raise `CfnHandlerError` when `boto3` is unavailable; include guard against retry-loop bug fixed in upstream #20/#34/#39/#51.
- [ ] 3.9 Create `src/cfn_handler/resource.py` implementing `CustomResource` with `create`/`update`/`delete`/`poll_create`/`poll_update`/`poll_delete` decorators, `__call__(event, context)` dispatch, double-registration `ValueError`, default-vs-override `physical_resource_id`, `no_echo` flag, init-failure handling (#7/#67), test-mode flag (#52/#54), `LambdaContext` Protocol type (#76), and the `log_level` accepted type fix (#66).
- [ ] 3.10 Verify mypy strict and pyright strict both pass on `src/cfn_handler/` with zero errors.

## 4. Tests

- [ ] 4.1 Create `tests/__init__.py` and `tests/conftest.py` with shared fixtures: `mock_context` (LambdaContext-like), autouse `aws_region_env` (monkeypatch `AWS_DEFAULT_REGION`), and `events` fixture loading JSON from `tests/events/`.
- [ ] 4.2 Create `tests/events/{create,update,delete}.json` with realistic CFN custom-resource event shapes.
- [ ] 4.3 Create `tests/unit/test_resource.py` covering: decorator registration, double-registration ValueError, dispatch by RequestType, unknown RequestType, missing-handler, return-value-as-data, `physical_resource_id` defaults and overrides, `no_echo`.
- [ ] 4.4 Create `tests/unit/test_response.py` covering: `build_response` payload shape per request type, `Reason` truncation at 4096 chars, `send_response` happy path, `send_response` raises `ResponseError` chained from `urllib` errors.
- [ ] 4.5 Create `tests/unit/test_poller.py` covering: poll decorator registration, defer-response when poll registered, re-invocation routing, terminal SUCCESS/FAIL response sending, CloudWatch Events rule cleanup, boto3-missing error.
- [ ] 4.6 Create `tests/unit/test_state_machine.py` using `hypothesis.stateful.RuleBasedStateMachine` modeling: handler-set × request-type × time-remaining × handler-outcome → expected response state. Use `@settings(deadline=None, max_examples=200)`.
- [ ] 4.7 Create `tests/integration/test_lambda_lifecycle.py` using `moto` (CloudWatch Events + a fake response endpoint) to drive a full CREATE-with-poll lifecycle end-to-end.
- [ ] 4.8 Run `uv run pytest --cov` and verify ≥95% line + branch coverage; fix any uncovered code paths or add `# pragma: no cover` only for truly impractical paths (with comment explaining why).
- [ ] 4.9 Verify all 14 fixed-upstream-issue scenarios are covered by named tests (mapped 1:1 to issue numbers in test docstrings or pytest IDs).

## 5. Examples

- [ ] 5.1 Create `examples/basic/template.yaml` (SAM) and `examples/basic/src/handler.py` showing a minimal Create/Update/Delete handler with no polling.
- [ ] 5.2 Create `examples/polled/template.yaml` and `examples/polled/src/handler.py` showing a long-running operation with `poll_create` and a fake "wait for ready" loop.
- [ ] 5.3 Create `examples/with-physical-id/template.yaml` and `examples/with-physical-id/src/handler.py` demonstrating explicit `physical_resource_id` override and UPDATE-as-replacement.
- [ ] 5.4 Create `examples/failing/template.yaml` and `examples/failing/src/handler.py` showing handler raising and resulting FAILED response.
- [ ] 5.5 Add `examples/README.md` indexing the four examples with one-line summaries.
- [ ] 5.6 Wire `cfn-lint` over `examples/**/template.yaml` into the CI lint job.

## 6. Justfile

- [ ] 6.1 Create `justfile` with recipes: `default` (list), `test`, `test-cov`, `test-watch`, `lint`, `lint-fix`, `format`, `mypy`, `pyright`, `typecheck` (mypy && pyright), `lock`, `sync`, `build`, `build-inspect`, `clean`, `cfn-lint`.
- [ ] 6.2 Add `test-matrix`, `test-matrix-amd64`, `test-matrix-arm64` recipes that drive `act` against `ci.yml` (parallel-safe, separate `--action-cache-path` per arch).
- [ ] 6.3 Verify `just --list` shows all recipes and each runs successfully on a clean checkout.

## 7. Nix flake

- [ ] 7.1 Create `flake.nix` using `flake-parts` and `import-tree` (dendritic style), declaring inputs (nixpkgs, flake-parts, import-tree).
- [ ] 7.2 Create `flake/devshells/default.nix` exposing `devShells.default` with: python3.12, uv, just, ruff, gh, act, cfn-lint binaries.
- [ ] 7.3 Add `flake.lock` via `nix flake lock`.
- [ ] 7.4 Verify `nix develop` enters a working shell and `uv sync --all-groups && just test` succeeds inside it.

## 8. GitHub Actions workflows

- [ ] 8.1 Create `.github/workflows/ci.yml`: trigger on PR + push to main; jobs `test` (matrix linux/amd64+arm64 × py3.10–3.14) and `lint` (single, py3.12, runs ruff check + ruff format --check + mypy + pyright + cfn-lint over examples); concurrency cancel-in-progress on PRs; permissions `contents: read`; all third-party actions SHA-pinned.
- [ ] 8.2 Create `.github/workflows/release.yml`: release-please opens release PR; on merge of release PR, build wheel+sdist via `uv build`, upload to GH Release artifacts, publish to PyPI via OIDC Trusted Publishing in environment `pypi`; permissions per-job least-privilege; `workflow_dispatch:` trigger included for manual re-runs.
- [ ] 8.3 Create `.github/workflows/codeql.yml`: schedule weekly + push to main; CodeQL init and analyze for python; permissions `security-events: write`, `actions: read`.
- [ ] 8.4 Create `.github/workflows/dependency-review.yml`: trigger on PR; runs `actions/dependency-review-action` with allowed-licenses (Apache-2.0, MIT variants, BSD variants, Python-2.0, ISC, MPL); fail-on-scopes `runtime`.
- [ ] 8.5 Create `.github/workflows/secure-workflows.yml`: trigger on PR + push touching `.github/workflows/**`; runs `zgosalvez/github-actions-ensure-sha-pinned-actions` with allowlist (none for now); fails the PR on tag-pinned actions.
- [ ] 8.6 Create `.github/dependabot.yml`: weekly groups `dev-dependencies` (ruff, mypy, pyright, pytest, pytest-cov, hypothesis, moto, coverage), `github-actions: *`; commit-message prefix `chore`, include scope.
- [ ] 8.7 Create `.github/ISSUE_TEMPLATE/bug_report.yml`, `.github/ISSUE_TEMPLATE/feature_request.yml`, and `.github/ISSUE_TEMPLATE/config.yml` (blank issues disabled, link to discussions).
- [ ] 8.8 Create `.github/PULL_REQUEST_TEMPLATE.md` with sections: Issue, Summary, Changes, Tests, Conventional commit reminder.
- [ ] 8.9 Create `release-please-config.json` and `.release-please-manifest.json` configured for `cfn-handler` package, type `python`, extra-files including `pyproject.toml`.

## 9. Verification & first commit

- [ ] 9.1 From a clean checkout: `nix develop` (if Nix user) or `uv sync --all-groups` succeeds.
- [ ] 9.2 `just lint` passes (ruff check + ruff format --check + cfn-lint).
- [ ] 9.3 `just typecheck` passes (mypy strict + pyright strict, zero errors).
- [ ] 9.4 `just test-cov` passes with ≥95% line + branch coverage.
- [ ] 9.5 `uv build` produces a valid wheel + sdist; `uv run twine check dist/*` reports OK.
- [ ] 9.6 `act -j test --matrix python-version:3.12` runs the matrix locally without GitHub.
- [ ] 9.7 Stage all files; review `git status` and `git diff --cached` to confirm no stray files; `git commit -m "feat: initial release (inspired by aws-cloudformation/custom-resource-helper)"`.

## 10. Remote setup & first release

- [ ] 10.1 Create the GitHub repo `igorlg/cfn-handler` via `gh repo create` (public, no autoinit, license placeholder declined since LICENSE is committed).
- [ ] 10.2 Push `main` to the new remote.
- [ ] 10.3 Verify CI workflows run green on the initial push.
- [ ] 10.4 Configure PyPI Trusted Publisher binding (`igorlg/cfn-handler`, `release.yml`, environment `pypi`).
- [ ] 10.5 Wait for release-please to open the v1.0.0 release PR; merge it.
- [ ] 10.6 Verify wheel and sdist appear on the GitHub Release; verify package appears on PyPI; verify `pip install cfn-handler && python -c "import cfn_handler; print(cfn_handler.__version__)"` shows `1.0.0`.
- [ ] 10.7 Update `igorlg/custom-resource-helper` README to point at the new repo; archive the old repo via `gh repo archive`.
- [ ] 10.8 Archive this OpenSpec change with `openspec archive bootstrap-v1-0-0`, which moves specs to `openspec/specs/` and the change to `openspec/changes/archive/`.
