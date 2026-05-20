# Default dev shell for cfn-handler contributors.
#
# Provides the system-level tooling needed to develop, test, lint, build,
# and release the library. Python itself is managed by `uv` — we only ship
# a system Python so uv has something to detect on the PATH; uv will
# transparently download its own interpreters when needed.
#
# Enter the shell with:
#   nix develop
#
# Then:
#   uv sync --all-groups
#   just test
{
  perSystem =
    { pkgs, ... }:
    {
      devShells.default = pkgs.mkShellNoCC {
        name = "cfn-handler-dev";

        packages = with pkgs; [
          # Python ecosystem
          uv
          python312          # baseline for type-checking; uv handles 3.10–3.14 matrix.

          # Task runner
          just

          # Linters / static analysis
          cfn-lint           # for examples/**/template.yaml validation

          # AWS / GitHub tooling
          awscli2
          gh

          # Local CI (matches `just test-matrix`)
          act

          # Container runtime needed by act on Linux. macOS contributors
          # already have Docker Desktop or OrbStack installed; on Linux the
          # `docker` package + `dockerd` running is required.
          # docker  # uncomment if your host is NixOS without docker installed

          # Utilities
          jq
          nodejs_20          # cfn-lint / act helpers occasionally invoke node
        ];

        shellHook = ''
          echo ""
          echo "  cfn-handler dev shell"
          echo "  ────────────────────────────────────────"
          echo "  uv:        $(uv --version)"
          echo "  just:      $(just --version)"
          echo "  python:    $(python3 --version)"
          echo "  cfn-lint:  $(cfn-lint --version 2>/dev/null || echo not found)"
          echo "  gh:        $(gh --version | head -1)"
          echo "  act:       $(act --version 2>/dev/null | head -1 || echo not found)"
          echo ""
          echo "  Quickstart:  uv sync --all-groups && just test"
          echo "  Recipes:     just --list"
          echo ""
        '';
      };
    };
}
