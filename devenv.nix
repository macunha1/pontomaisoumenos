{
  pkgs,
  lib,
  config,
  ...
}:
{
  languages.python = {
    enable = true;
    lsp.enable = false;
    uv.enable = true;
    uv.sync.enable = false;
  };
  packages = [
    pkgs.coreutils
    pkgs.nixfmt
    pkgs.sqlite
    pkgs.actionlint
  ];
  dotenv.disableHint = true;
  dotenv.enable = false;

  env = {
    UV_PYTHON = config.languages.python.package.interpreter;
    UV_PYTHON_DOWNLOADS = "never";
    # Avoid the flake compatibility wrapper re-entering without --no-update-lock-file.
    DEVENV_IN_DIRENV_SHELL = "true";
  }
  // lib.optionalAttrs pkgs.stdenv.hostPlatform.isLinux {
    LD_LIBRARY_PATH = lib.makeLibraryPath [ pkgs.stdenv.cc.cc.lib ];
  };

  tasks = {
    "app:install".exec = "uv sync --locked";
    "app:lint" = {
      after = [ "app:install" ];
      exec = ''
        uv run --locked --no-env-file ruff check .
        uv run --locked --no-env-file ruff format --check .
        nixfmt --check flake.nix devenv.nix shell.nix
        actionlint
      '';
    };
    "app:typecheck" = {
      after = [ "app:install" ];
      exec = "uv run --locked --no-env-file ty check --error-on-warning";
    };
    "app:test" = {
      after = [ "app:install" ];
      exec = "uv run --locked --no-env-file pytest";
    };
    "app:check".after = [
      "app:lint"
      "app:typecheck"
      "app:test"
    ];
    "app:build" = {
      after = [ "app:check" ];
      exec = ''
        rm -f dist/pontomaisoumenos-*.whl dist/pontomaisoumenos-*.tar.gz dist/SHA256SUMS
        uv run --locked --no-env-file python -m build --no-isolation
      '';
    };
    "app:verify" = {
      after = [ "app:build" ];
      exec = ''
        uv run --locked --no-env-file python scripts/verify_distribution.py
        uv export --locked --no-dev --no-emit-project --output-file dist/requirements.txt
        cd dist
        sha256sum pontomaisoumenos-*.whl pontomaisoumenos-*.tar.gz requirements.txt > SHA256SUMS
        sha256sum --check SHA256SUMS
      '';
    };
    "app:ci".after = [ "app:verify" ];
    "app:image".exec = ''
      (cd dist && sha256sum --check SHA256SUMS)
      docker build -t pontomaisoumenos:test .
      docker run --rm pontomaisoumenos:test --help
      docker run --rm --entrypoint sh pontomaisoumenos:test -c 'python -m pontomaisoumenos migrate && test -s pontomaisoumenos.db'
    '';
    "app:migrate" = {
      after = [ "app:install" ];
      exec = "uv run --locked --env-file .env pontomaisoumenos --config config/default.toml migrate";
    };
    "app:dev" = {
      after = [ "app:migrate" ];
      exec = "uv run --locked --env-file .env pontomaisoumenos --config config/default.toml serve";
    };
    "devenv:enterTest".after = [ "app:ci" ];
  };

  processes.application.exec = "devenv tasks run app:dev";
  enterTest = ''
    python --version
    uv --version
  '';
}
