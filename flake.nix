{
  description = "cfn-handler — modern CloudFormation Custom Resource lifecycle handler for AWS Lambda";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    flake-parts.inputs.nixpkgs-lib.follows = "nixpkgs";
    import-tree.url = "github:vic/import-tree";
  };

  # Dendritic / flake-parts style: the flake.nix is a thin shim. All real
  # configuration lives under `./flake/` and is auto-imported by `import-tree`.
  # Convention: drop a `.nix` file anywhere under `./flake/` and it becomes
  # a flake-parts module ("import == enable").
  outputs =
    inputs@{ flake-parts, import-tree, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      imports = [ (import-tree ./flake) ];
    };
}
