"""Validated process configuration, resolved only at startup."""

from functools import cached_property
from pathlib import Path
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, SecretStr, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    SettingsError,
    TomlConfigSettingsSource,
)

from .holidays import DEFAULT_ENABLED_OPTIONAL_HOLIDAYS, OptionalHoliday

type PositiveInt = Annotated[int, Field(gt=0)]


class WorkingHours(BaseModel):
    possible_minutes_variation_start: int = Field(default=0, ge=0, le=59)
    possible_minutes_variation_end: int = Field(default=59, ge=1, le=60)
    possible_start_hour: int = Field(default=9, ge=0, le=23)
    lunch_time: float = Field(default=1, ge=0, lt=24)
    accepted_start_hour_variation: float = Field(default=1.23, gt=0)
    maximum_daily_working_hours: float = Field(default=10, gt=0, lt=24)
    expected_daily_hours: float = Field(default=8.8, gt=0, lt=24)

    @model_validator(mode="after")
    def validate_ranges(self) -> Self:
        if self.possible_minutes_variation_start >= self.possible_minutes_variation_end:
            raise ValueError("The minute range must be nonempty (end is exclusive)")
        if self.expected_daily_hours > self.maximum_daily_working_hours:
            raise ValueError("Expected hours must not exceed maximum daily hours")
        if self.maximum_daily_working_hours + self.lunch_time >= 24:
            raise ValueError("Working hours plus lunch must fit in one day")
        return self


class Location(BaseModel):
    address: str = ""
    latitude: float = Field(default=0, ge=-90, le=90)
    longitude: float = Field(default=0, ge=-180, le=180)


class UserCredentials(BaseModel):
    email: str = ""
    password: SecretStr = SecretStr("")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PM_", env_nested_delimiter="__", extra="forbid", hide_input_in_errors=True
    )

    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///pontomaisoumenos.db")
    broker: Literal["memory", "redis"] = "memory"
    redis_url: SecretStr = SecretStr("redis://localhost:36379/0")
    redis_namespace: str = "pontomaisoumenos-v2"
    timezone: str = "America/Sao_Paulo"
    holiday_subdivision: str = "SP"
    enabled_optional_holidays: tuple[OptionalHoliday, ...] = DEFAULT_ENABLED_OPTIONAL_HOLIDAYS
    log_level: str = "INFO"
    working_hours: WorkingHours = Field(default_factory=WorkingHours)
    location: Location = Field(default_factory=Location)
    user: UserCredentials = Field(default_factory=UserCredentials)
    api_url: str = "https://api.pontomais.com.br"
    http_timeout_seconds: float = Field(default=20, gt=0, le=120)
    http_max_connections: PositiveInt = 16
    database_pool_size: PositiveInt = 5
    worker_processes: PositiveInt = 1
    worker_threads: PositiveInt = 16
    poll_interval_seconds: float = Field(default=10, gt=0)
    dispatch_horizon_seconds: PositiveInt = 60
    delivery_lease_seconds: PositiveInt = 300
    max_lateness_seconds: PositiveInt = 900
    dispatch_batch_size: PositiveInt = 100

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return env_settings, init_settings, dotenv_settings, file_secret_settings

    @cached_property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @model_validator(mode="after")
    def validate_runtime(self) -> Self:
        ZoneInfo(self.timezone)
        if self.broker == "memory" and self.worker_processes != 1:
            raise ValueError("The memory broker requires one process; use worker_threads for concurrency")
        if self.delivery_lease_seconds <= self.dispatch_horizon_seconds + self.http_timeout_seconds * 3:
            raise ValueError("Delivery lease must exceed the dispatch horizon plus the job deadline")
        if self.max_lateness_seconds <= self.delivery_lease_seconds:
            raise ValueError("Maximum lateness must exceed the delivery lease")
        if self.log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("Invalid log level")
        return self

    def require_credentials(self) -> None:
        if not self.user.email or not self.user.password.get_secret_value():
            raise SettingsError("Set PM_USER__EMAIL and PM_USER__PASSWORD before starting the service")


def load_settings(config_path: Path | None = None) -> Settings:
    """Environment values override the optional, explicitly located TOML file."""
    if config_path is None:
        return Settings()
    if not config_path.is_file():
        raise SettingsError(f"Configuration file does not exist: {config_path}")
    source = TomlConfigSettingsSource(Settings, toml_file=config_path)
    # Settings' environment source takes precedence over defaults supplied here.
    return Settings(**source())
