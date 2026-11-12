{
  description = "PontoMais application development and CI";

  inputs = {
    nixpkgs.url = "github:cachix/devenv-nixpkgs/rolling";
    devenv = {
      url = "github:cachix/devenv/v2.4.0";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  nixConfig = {
    extra-substituters = [ "https://devenv.cachix.org" ];
    extra-trusted-public-keys = [
      "devenv.cachix.org-1:w1cLUi8dv3hnoSPGAuibQv+f9TZLr6cv/Hm9XgU50cw="
    ];
  };

  outputs =
    { nixpkgs, devenv, ... }@inputs:
    let
      forSystems = nixpkgs.lib.genAttrs [
        "x86_64-linux"
        "aarch64-linux"
        "aarch64-darwin"
      ];
    in
    {
      devShells = forSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          shell =
            name: python:
            devenv.lib.mkShell {
              inherit inputs pkgs;
              modules = [
                ./devenv.nix
                {
                  _module.args.name = name;
                  languages.python.package = python;
                }
              ];
            };
        in
        rec {
          default = python314;
          python314 = shell "python314" pkgs.python314;
          python315 = shell "python315" pkgs.python315;
        }
      );
      formatter = forSystems (system: nixpkgs.legacyPackages.${system}.nixfmt);
    };
}
