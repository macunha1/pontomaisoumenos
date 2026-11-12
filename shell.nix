# Compatibility for nix-shell/lorri; flake.lock owns every Nix input.
(builtins.getFlake (toString ./.)).devShells.${builtins.currentSystem}.default
