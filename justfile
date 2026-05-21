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
# Uses `pull_request` event because ci.yml is PR-only (no push:main trigger).
test-matrix: _check-act
    #!/usr/bin/env bash
    set -uo pipefail
    echo "Running amd64 and arm64 jobs in parallel via act..."
    act pull_request -j test --container-architecture linux/amd64 --matrix runner:ubuntu-24.04 \
        --action-cache-path /tmp/act-cache-amd64 &
    pids=("$!")
    act pull_request -j test --container-architecture linux/arm64 --matrix runner:ubuntu-24.04-arm \
        --action-cache-path /tmp/act-cache-arm64 &
    pids+=("$!")
    failed=0
    for pid in "${pids[@]}"; do
      wait "$pid" || failed=1
    done
    exit "$failed"

test-matrix-amd64: _check-act
    act pull_request -j test --container-architecture linux/amd64 --matrix runner:ubuntu-24.04

test-matrix-arm64: _check-act
    act pull_request -j test --container-architecture linux/arm64 --matrix runner:ubuntu-24.04-arm

# Run every GH Actions job that gates merging a PR to main (Dependabot vet).
#
# Sequential, fail-fast, no side effects. Skipped: dependency-review.yml
# (needs PR context act can't synthesize). Requires `act`, `gh` (authenticated),
# and `docker`.
#
# Steps (each on a fresh container):
#   1. secure-workflows.yml — re-validate SHA pinning of every action
#      (~5s). Catches tag-pinned bumps.
#   2. Docker action manifest probe — for every Docker-based action used
#      anywhere in .github/workflows/, verify the pinned commit SHA
#      resolves to a real ghcr.io image (~2s). Catches the
#      annotated-tag-SHA-on-Docker-action class of bug (the v1.0.0
#      release failure) without invoking release.yml — which would
#      have real side effects on the repo (release-please-action
#      authenticated as the user could open or update real release PRs).
#   3a. ci.yml `test` matrix — amd64 + arm64 × 5 Python versions (~3-5 min).
#   3b. ci.yml `lint` job — ruff, ruff-format, mypy strict, pyright strict
#       (~30s).
#   3c. examples-lint.yml — cfn-lint over examples/**/template.yaml (~30s).
#   4. codeql.yml — Python security-and-quality scan (~1-8 min, slower
#      on first run while CodeQL bundle downloads).
gha-pre-release: _check-act _check-gh-token _check-docker
    #!/usr/bin/env bash
    set -uo pipefail

    common_flags=(
      --container-architecture linux/amd64
      --secret GITHUB_TOKEN="$(gh auth token)"
    )

    echo "==> [1/6] secure-workflows.yml — SHA-pin enforcement"
    act pull_request -W .github/workflows/secure-workflows.yml "${common_flags[@]}" \
        --action-cache-path /tmp/act-cache-secure-workflows \
        || { echo; echo "FAIL: secure-workflows.yml"; exit 1; }

    echo
    echo "==> [2/6] Docker action manifest probe"
    # Match `uses: <owner>/<repo>@<sha>` in every workflow file, then for any
    # action that publishes a Docker image at ghcr.io/<owner>/<repo>, verify
    # the SHA resolves to a real image. Currently this is just
    # pypa/gh-action-pypi-publish; the loop is data-driven so any new
    # Docker actions added to workflows are checked automatically.
    docker_actions_with_images=(
      "pypa/gh-action-pypi-publish"
    )
    failed_manifests=()
    for action in "${docker_actions_with_images[@]}"; do
      shas=$(grep -hE "uses: ${action}@[a-f0-9]{40}" .github/workflows/*.yml \
              | grep -oE "[a-f0-9]{40}" | sort -u)
      if [[ -z "$shas" ]]; then
        echo "  (action ${action} not in use; skipping)"
        continue
      fi
      while IFS= read -r sha; do
        image="ghcr.io/${action}:${sha}"
        printf "  probe %-80s ... " "$image"
        if docker manifest inspect "$image" >/dev/null 2>&1; then
          echo "OK"
        else
          echo "MISSING"
          failed_manifests+=("$image")
        fi
      done <<< "$shas"
    done
    if (( ${#failed_manifests[@]} > 0 )); then
      echo
      echo "FAIL: Docker manifest probe — these images do not resolve:"
      printf '  - %s\n' "${failed_manifests[@]}"
      echo
      echo "This is the v1.0.0 release-failure bug class: a Docker action was"
      echo "pinned to its annotated-tag-object SHA instead of the commit SHA."
      echo "Resolve the correct commit SHA via:"
      echo "  gh api /repos/<owner>/<repo>/git/tags/\$(gh api /repos/<owner>/<repo>/git/ref/tags/<tag> --jq '.object.sha') --jq '.object.sha'"
      exit 1
    fi
    echo "  (all Docker action images resolve)"

    echo
    echo "==> [3a/6] ci.yml — test matrix (amd64 + arm64 in parallel)"
    just test-matrix \
        || { echo; echo "FAIL: ci.yml test matrix"; exit 1; }

    echo
    echo "==> [3b/6] ci.yml — lint+typecheck job"
    act pull_request -W .github/workflows/ci.yml "${common_flags[@]}" --job lint \
        --action-cache-path /tmp/act-cache-lint \
        || { echo; echo "FAIL: ci.yml lint job"; exit 1; }

    echo
    echo "==> [3c/6] examples-lint.yml — cfn-lint over examples"
    act pull_request -W .github/workflows/examples-lint.yml "${common_flags[@]}" \
        --action-cache-path /tmp/act-cache-examples-lint \
        || { echo; echo "FAIL: examples-lint.yml"; exit 1; }

    echo
    echo "==> [4/6] codeql.yml — Python security analysis"
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

_check-docker:
    @command -v docker >/dev/null || { echo 'error: docker not installed. Install Docker Desktop, OrbStack, or Colima.'; exit 1; }
    @docker info >/dev/null 2>&1 || { echo 'error: docker daemon not running.'; exit 1; }
