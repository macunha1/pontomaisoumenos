import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from pydantic_settings import SettingsError

from pontomaisoumenos.settings import Settings, load_settings


def test_toml_environment_override_and_explicit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = tmp_path / "settings.toml"
    config.write_text('[user]\nemail = "file@example.com"\npassword = "file-password"\n[location]\nlatitude = 12.5\n')
    monkeypatch.setenv("PM_USER__EMAIL", "env@example.com")
    monkeypatch.setenv("PM_DATABASE_URL", "postgresql+psycopg://other:password@localhost/database")
    monkeypatch.chdir("/tmp")
    settings = load_settings(config)
    assert settings.user.email == "env@example.com"
    assert settings.user.password.get_secret_value() == "file-password"
    assert settings.location.latitude == 12.5
    assert "other:" in settings.database_url.get_secret_value()
    assert "file-password" not in repr(settings)


def test_optional_holidays_accept_toml_and_json_environment_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "settings.toml"
    config.write_text('enabled_optional_holidays = ["carnival", "corpus_christi"]\n')
    assert Settings().enabled_optional_holidays == ("carnival",)
    assert load_settings(config).enabled_optional_holidays == ("carnival", "corpus_christi")
    monkeypatch.setenv("PM_ENABLED_OPTIONAL_HOLIDAYS", "[]")
    assert load_settings(config).enabled_optional_holidays == ()
    monkeypatch.setenv("PM_ENABLED_OPTIONAL_HOLIDAYS", '["ash_wednesday", "christmas_eve"]')
    assert load_settings(config).enabled_optional_holidays == ("ash_wednesday", "christmas_eve")
    monkeypatch.setenv("PM_ENABLED_OPTIONAL_HOLIDAYS", '["carnaval"]')
    with pytest.raises(ValidationError, match="enabled_optional_holidays"):
        load_settings(config)


def test_configuration_errors_are_early_and_secrets_are_hidden() -> None:
    with pytest.raises(ValidationError, match="Invalid log level") as caught:
        Settings(log_level="NOT-A-LEVEL", database_url=SecretStr("sensitive-url"))
    assert "sensitive-url" not in str(caught.value)
    with pytest.raises(ValidationError, match="Maximum lateness"):
        Settings(max_lateness_seconds=1)
    with pytest.raises(SettingsError, match="does not exist"):
        load_settings(Path("/missing/settings.toml"))
    with pytest.raises(SettingsError, match="PM_USER__EMAIL"):
        Settings().require_credentials()


def test_imports_do_not_connect_load_configuration_or_configure_logging(tmp_path: Path) -> None:
    script = """
import importlib, logging, socket
def fail(*args, **kwargs):
    raise AssertionError('Import attempted network IO')
socket.socket.connect = fail
before = list(logging.getLogger().handlers)
for module in ['settings', 'database', 'pontomais', 'worker', 'scheduling', 'cli']:
    importlib.import_module('pontomaisoumenos.' + module)
assert before == list(logging.getLogger().handlers)
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert not result.stdout


def test_installed_cli_help_from_outside_checkout(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pontomaisoumenos", "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "schedule" in result.stdout
    assert "reconcile" in result.stdout


def test_sqlite_and_memory_defaults_and_process_limit() -> None:
    settings = Settings()
    assert settings.database_url.get_secret_value() == "sqlite+aiosqlite:///pontomaisoumenos.db"
    assert settings.broker == "memory"
    with pytest.raises(ValidationError, match="requires one process"):
        Settings(worker_processes=2)
    assert Settings(broker="redis", worker_processes=2).worker_processes == 2
