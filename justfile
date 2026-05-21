# cfn-handler — task runner
# Run `just` (or `just --list`) to see available recipes.

set shell := ["bash", "-uc"]

default:
    @just --list

# ---- Tests ----------------------------------------------------------------

# Run the test suite (unit + integration), no coverage gate.
test:
    uv run pytest

# Run only unit tests (fast iteration loop).
test-unit:
    uv run pytest tests/unit

# Run integration tests only.
test-integration:
    uv run pytest tests/integration

# Run the test suite with coverage gate (fails below 95%).
test-cov:
    uv run pytest --cov --cov-report=term-missing --cov-report=html

# Watch tests (re-run on file change). Requires pytest-watcher; install via `uv add --group test pytest-watcher` if not already.
test-watch:
    uv run pytest --looponfail

# ---- Lint + type-check ----------------------------------------------------

# Lint (ruff check + ruff format check + cfn-lint over examples). Same checks as CI.
lint: lint-ruff lint-cfn

# Ruff lint + format-check (no autofix).
lint-ruff:
    uv run ruff check src tests examples
    uv run ruff format src tests examples --check

# cfn-lint over example SAM templates.
lint-cfn:
    uv run cfn-lint examples/**/template.yaml

# Auto-fix ruff issues with safe fixes; re-run lint after.
lint-fix:
    uv run ruff check --fix src tests examples
    uv run ruff format src tests examples

# Run mypy strict over the source tree.
mypy:
    uv run mypy src/cfn_handler

# Run pyright strict over the source tree.
pyright:
    uv run pyright src/cfn_handler

# Run both type-checkers (mypy strict + pyright strict).
typecheck: mypy pyright

# Run every check CI runs, in CI order. Fails fast.
ci-check: lint typecheck test-cov

# ---- Build ----------------------------------------------------------------

# Refresh uv.lock after pyproject.toml changes.
lock:
    uv lock

# Sync all dependency groups into the local .venv.
sync:
    uv sync --all-groups

# Build sdist + wheel into ./dist.
build:
    uv build

# Build and inspect contents of the wheel + sdist (sanity check py.typed shipped).
build-inspect: build
    @echo "--- wheel contents ---"
    @unzip -l dist/*.whl
    @echo
    @echo "--- sdist contents ---"
    @tar -tzf dist/*.tar.gz

# ---- Local CI matrix via act ---------------------------------------------

# Run the GH Actions matrix locally (linux/amd64 + arm64). Requires `act`:
#   brew install act
test-matrix: _check-act
    #!/usr/bin/env bash
    set -uo pipefail
    echo "Running amd64 and arm64 jobs in parallel via act..."
    act -j test --container-architecture linux/amd64 --matrix runner:ubuntu-24.04 \
        --action-cache-path /tmp/act-cache-amd64 &
    pids=("$!")
    act -j test --container-architecture linux/arm64 --matrix runner:ubuntu-24.04-arm \
        --action-cache-path /tmp/act-cache-arm64 &
    pids+=("$!")
    failed=0
    for pid in "${pids[@]}"; do
      wait "$pid" || failed=1
    done
    exit "$failed"

test-matrix-amd64: _check-act
    act -j test --container-architecture linux/amd64 --matrix runner:ubuntu-24.04

test-matrix-arm64: _check-act
    act -j test --container-architecture linux/arm64 --matrix runner:ubuntu-24.04-arm

# Run every GH Actions job that gates merging a PR to main (Dependabot vet).
#
# Sequential, fail-fast. Skipped: dependency-review.yml (needs PR context
# that act can't synthesize). Requires `act` and an authenticated `gh` CLI.
#
# Steps (each on a fresh container):
#   1. secure-workflows.yml — re-validate SHA pinning of every action.
#      ~5s. Catches tag-pinned or annotated-tag-SHA bumps.
#   2. release.yml `release-please` job — exercise release-please-action
#      against the real GitHub API. ~10s. Catches the "release.yml runs
#      only on push to main, never tested by PR CI" gap.
#   3. ci.yml — full matrix (amd64 + arm64) + lint+typecheck. ~3-5 min.
#   4. codeql.yml — Python security-and-quality scan. ~1-8 min (slower
#      on first run while CodeQL bundle downloads).
gha-pre-release: _check-act _check-gh-token
    #!/usr/bin/env bash
    set -uo pipefail

    common_flags=(
      --container-architecture linux/amd64
      --secret GITHUB_TOKEN="$(gh auth token)"
    )

    echo "==> [1/4] secure-workflows.yml — SHA-pin enforcement"
    act push -W .github/workflows/secure-workflows.yml "${common_flags[@]}" \
        --action-cache-path /tmp/act-cache-secure-workflows \
        || { echo; echo "FAIL: secure-workflows.yml"; exit 1; }

    echo
    echo "==> [2/4] release.yml — release-please-action dry-run (real GH API)"
    act push -W .github/workflows/release.yml "${common_flags[@]}" --job release-please \
        --action-cache-path /tmp/act-cache-release-please \
        || { echo; echo "FAIL: release.yml release-please job"; exit 1; }

    echo
    echo "==> [3/4] ci.yml — full matrix (amd64 + arm64) + lint+typecheck"
    just test-matrix \
        || { echo; echo "FAIL: ci.yml matrix"; exit 1; }

    echo
    echo "==> [4/4] codeql.yml — Python security analysis"
    act push -W .github/workflows/codeql.yml "${common_flags[@]}" \
        --action-cache-path /tmp/act-cache-codeql \
        || { echo; echo "FAIL: codeql.yml"; exit 1; }

    echo
    echo "OK: all gating jobs passed locally. Safe to merge."

# ---- OpenSpec ------------------------------------------------------------

# List active OpenSpec changes.
openspec-list:
    openspec list

# Validate every change strictly.
openspec-validate:
    @for change in openspec/changes/*/; do \
        name=$(basename "$change"); \
        if [ "$name" != "archive" ]; then \
            echo ">> $name"; \
            openspec validate "$name" --strict; \
        fi; \
    done

# ---- Cleanup -------------------------------------------------------------

# Remove build artifacts and caches.
clean:
    rm -rf dist build htmlcov .coverage .coverage.* coverage.xml
    rm -rf .pytest_cache .mypy_cache .ruff_cache .hypothesis
    find . -type d -name __pycache__ -prune -exec rm -rf {} +
    find . -type d -name '*.egg-info' -prune -exec rm -rf {} +

# ---- Internal recipes ----------------------------------------------------

_check-act:
    @command -v act >/dev/null || { echo 'error: act not installed. Install with: brew install act'; exit 1; }

_check-gh-token:
    @gh auth token >/dev/null 2>&1 || { echo 'error: gh CLI not authenticated. Run: gh auth login'; exit 1; }
