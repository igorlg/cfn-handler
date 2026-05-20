# Supported systems for the flake outputs.
# Adding a system here makes every output (devShells, packages, etc.) build
# for that system.
{
  systems = [
    "aarch64-darwin"
    "x86_64-darwin"
    "aarch64-linux"
    "x86_64-linux"
  ];
}
