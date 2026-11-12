"""Installed process commands; imports do not resolve configuration or start IO."""

import argparse
import asyncio
import logging
import os
import signal
import sys
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

import dramatiq
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from pydantic_settings import SettingsError
from sqlalchemy import select

from .database import Database, Punch, utc_now
from .scheduling import Scheduler
from .settings import Settings, load_settings
from .worker import configure_broker


async def run_scheduler(
    settings: Settings, *, once: bool = False, workers: bool = False, generate: bool = True
) -> None:
    database = Database(settings)
    broker = configure_broker(settings)
    scheduler = Scheduler(settings, database.sessions, broker)
    worker = dramatiq.Worker(broker, worker_threads=settings.worker_threads) if workers else None
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stop.set)
    try:
        if worker is not None:
            await asyncio.to_thread(worker.start)
        if once:
            now = utc_now()
            await scheduler.ensure_month(now)
            if settings.broker == "redis":
                await scheduler.dispatch(now)
        else:
            await scheduler.run(stop, generate=generate, dispatch=workers or settings.broker == "redis")
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)
        if worker is not None:
            await asyncio.to_thread(worker.stop, timeout=round((settings.http_timeout_seconds * 3 + 5) * 1000))
        await database.close()
        await asyncio.to_thread(broker.close)


async def reconcile(settings: Settings, punch_id: str, outcome: Literal["done", "pending"]) -> None:
    database = Database(settings)
    try:
        async with database.sessions.begin() as session:
            punch = await session.scalar(select(Punch).where(Punch.id == punch_id).with_for_update())
            if punch is None or punch.status not in {"uncertain", "failed"}:
                raise ValueError("Only an uncertain or failed punch can be reconciled")
            punch.status = outcome
            punch.done = outcome == "done"
            punch.queued_at = None
            punch.updated_at = utc_now()
    finally:
        await database.close()


def migrate(settings: Settings, *, stamp_legacy: bool = False, legacy_timezone: str | None = None) -> None:
    """Migrations ship in the wheel and run independently of the checkout."""
    with as_file(files("pontomaisoumenos").joinpath("migrations")) as migration_path:
        config = Config()
        config.set_main_option("script_location", str(migration_path))
        config.attributes["database_url"] = settings.database_url.get_secret_value()
        config.attributes["legacy_timezone"] = legacy_timezone or settings.timezone
        if stamp_legacy:
            command.stamp(config, "0001")
        else:
            command.upgrade(config, "head")


def main() -> int:
    parser = argparse.ArgumentParser(description="PontoMais background job service")
    parser.add_argument("--config", type=Path, help="Explicit TOML configuration path (environment overrides it)")
    commands = parser.add_subparsers(dest="command", required=True)
    scheduler = commands.add_parser("schedule", help="Generate and dispatch monthly schedules continuously")
    scheduler.add_argument("--once", action="store_true", help="Run one scheduling tick, then exit")
    commands.add_parser("worker", help="Start Dramatiq's async worker")
    commands.add_parser("serve", help="Run scheduling and worker threads together (no Redis needed)")
    migrations = commands.add_parser("migrate", help="Upgrade the database schema")
    migrations.add_argument("--legacy-timezone", help="Timezone of timestamps written by the old application")
    migrations.add_argument(
        "--stamp-legacy", action="store_true", help="Mark a verified legacy schema as revision 0001"
    )
    reconciliation = commands.add_parser("reconcile", help="Record a verified remote outcome for a held punch")
    reconciliation.add_argument("punch_id")
    reconciliation.add_argument("outcome", choices=("done", "pending"))
    arguments = parser.parse_args()
    try:
        settings = load_settings(arguments.config)
        logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
        if arguments.command == "migrate":
            migrate(settings, stamp_legacy=arguments.stamp_legacy, legacy_timezone=arguments.legacy_timezone)
        elif arguments.command == "reconcile":
            asyncio.run(reconcile(settings, arguments.punch_id, arguments.outcome))
        else:
            settings.require_credentials()
            if arguments.command == "serve" or (arguments.command == "worker" and settings.broker == "memory"):
                asyncio.run(run_scheduler(settings, workers=True, generate=arguments.command == "serve"))
            elif arguments.command == "worker":
                if arguments.config:
                    os.environ["PM_CONFIG_FILE"] = str(arguments.config.resolve())
                os.execv(
                    sys.executable,
                    [
                        sys.executable,
                        "-m",
                        "dramatiq",
                        "pontomaisoumenos.worker:boot",
                        "--processes",
                        str(settings.worker_processes),
                        "--threads",
                        str(settings.worker_threads),
                    ],
                )
            else:
                asyncio.run(run_scheduler(settings, once=arguments.once))
    except (ValidationError, SettingsError) as error:
        parser.exit(2, f"Configuration error: {error}\n")
    except Exception as error:
        parser.exit(1, f"Command failed ({type(error).__name__}); check configuration and backing services\n")
    return 0
