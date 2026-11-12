"""Verify the built distribution through a regular install outside the checkout."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    wheels = list((root / "dist").glob("pontomaisoumenos-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError("Expected exactly one application wheel")
    with ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        required = {
            "pontomaisoumenos/py.typed",
            "pontomaisoumenos/migrations/env.py",
            "pontomaisoumenos/migrations/versions/0002_durable_delivery.py",
        }
        if not required <= names or any(name.startswith(("tests/", ".env")) for name in names):
            raise RuntimeError("The wheel does not meet its resource contract")

    environment = dict(os.environ)
    for name in tuple(environment):
        if name.startswith("PM_") or name in {"PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"}:
            environment.pop(name)
    environment["UV_NO_ENV_FILE"] = "1"
    with tempfile.TemporaryDirectory(prefix="pontomais-wheel-") as directory:
        workspace = Path(directory)
        python = workspace / "venv/bin/python"
        requirements = workspace / "requirements.txt"

        def run(*arguments: str, cwd: Path = workspace) -> None:
            subprocess.run(arguments, cwd=cwd, env=environment, check=True)

        run("uv", "venv", str(workspace / "venv"), "--python", sys.executable)
        run(
            "uv",
            "export",
            "--locked",
            "--no-emit-project",
            "--group",
            "dev",
            "--output-file",
            str(requirements),
            cwd=root,
        )
        run("uv", "pip", "sync", "--python", str(python), "--require-hashes", str(requirements))
        run("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheels[0]))
        run("uv", "pip", "check", "--python", str(python))
        run(str(python), "-c", "import pontomaisoumenos; assert '/venv/' in pontomaisoumenos.__file__")
        run(str(python), "-m", "pontomaisoumenos", "--help")
        run(str(python), "-m", "pontomaisoumenos", "migrate")
        run(str(python), "-m", "pytest", str(root / "tests"), "--import-mode=importlib")


if __name__ == "__main__":
    main()
