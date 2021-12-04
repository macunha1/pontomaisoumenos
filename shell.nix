with import <nixpkgs> {};

stdenv.mkDerivation {
  name = "pontomaisoumenos";

  buildInputs = [
    python39Full
    python39Packages.pytest
    python39Packages.flake8
    python39Packages.autopep8

    python39Packages.pandas
    python39Packages.numpy
    python39Packages.psycopg2

    python39Packages.setuptools
  ];
}
