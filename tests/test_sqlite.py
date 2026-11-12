"""File-backed SQLite claims and real in-process Dramatiq execution."""

import asyncio
import os
import signal
import sys
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from dramatiq import Worker
from pydantic import SecretStr
from sqlalchemy import select, text

from pontomaisoumenos.broker import MemoryBroker
from pontomaisoumenos.cli import migrate
from pontomaisoumenos.database import Database, Punch, User, utc_now
from pontomaisoumenos.pontomais import PontoMais
from pontomaisoumenos.processing import PunchProcessor
from pontomaisoumenos.runtime import Runtime
from pontomaisoumenos.scheduling import Scheduler
from pontomaisoumenos.settings import Settings
from pontomaisoumenos.worker import WorkerResources, configure_broker

from .test_http import LocalAPI, local_api  # noqa: F401 (shared loopback fixture)
from .test_scheduling import RecordingBroker


@pytest.fixture
async def sqlite(tmp_path: Path, settings: Settings) -> AsyncIterator[tuple[Settings, Database]]:
    settings = settings.model_copy(update={"database_url": SecretStr(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")})
    await asyncio.to_thread(migrate, settings)
    database = Database(settings)
    try:
        yield settings, database
    finally:
        await database.close()


async def seed(database: Database, settings: Settings) -> str:
    async with database.sessions.begin() as session:
        user = User(email=settings.user.email)
        session.add(user)
        await session.flush()
        punch = Punch(user_id=user.id, should_punch_at=utc_now() - timedelta(seconds=1))
        session.add(punch)
        await session.flush()
        return punch.id


async def test_sqlite_pragmas_and_concurrent_delivery(sqlite) -> None:
    settings, database = sqlite
    punch_id = await seed(database, settings)
    async with database.engine.connect() as connection:
        assert await connection.scalar(text("PRAGMA journal_mode")) == "wal"
        assert await connection.scalar(text("PRAGMA foreign_keys")) == 1
    submissions = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submissions += 1
        await asyncio.sleep(0.03)
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    # Independent engines represent separate worker processes sharing one file.
    other = Database(settings)
    try:
        async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
            first = PunchProcessor(settings, database.sessions, PontoMais(settings, http))
            second = PunchProcessor(settings, other.sessions, PontoMais(settings, http))
            await asyncio.gather(first.process(punch_id), second.process(punch_id))
        assert submissions == 1
    finally:
        await other.close()


async def test_sqlite_concurrent_generation_and_dispatch(sqlite) -> None:
    settings, database = sqlite
    other = Database(settings)
    broker = RecordingBroker()
    now = utc_now()
    first = Scheduler(settings, database.sessions, broker)
    second = Scheduler(settings, other.sessions, broker)
    try:
        await asyncio.gather(first.ensure_month(now), second.ensure_month(now))
        async with database.sessions() as session:
            punches = list(await session.scalars(select(Punch)))
            assert len({p.should_punch_at.date() for p in punches}) * 2 == len(punches)
        async with database.sessions.begin() as session:
            user = await session.scalar(select(User))
            session.add(Punch(user_id=user.id, should_punch_at=now - timedelta(seconds=1)))
        await asyncio.gather(first.dispatch(now), second.dispatch(now))
        ids = [message.args[0] for message, _ in broker.messages]
        assert len(ids) == len(set(ids))
        assert ids
    finally:
        await other.close()


async def test_lost_memory_queue_recovers_from_sqlite_after_restart(sqlite, monkeypatch) -> None:
    settings, database = sqlite
    punch_id = await seed(database, settings)
    lost_broker = configure_broker(settings)
    scheduler = Scheduler(settings, database.sessions, lost_broker)
    assert await scheduler.dispatch(utc_now()) == 1
    # Discard the broker and reopen the database; only durable state survives.
    lost_broker.flush_all()
    lost_broker.close()
    await database.close()
    restarted = Database(settings)
    submitted: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submitted.append(request.url.path)
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    monkeypatch.setattr(
        "pontomaisoumenos.worker.Runtime",
        lambda configuration: Runtime(configuration, transport=httpx.MockTransport(handle)),
    )
    broker = configure_broker(settings)
    worker = Worker(broker, worker_threads=2, worker_timeout=100)
    resources = next(item for item in broker.middleware if isinstance(item, WorkerResources))
    try:
        await asyncio.to_thread(worker.start)
        assert resources.runtime is not None
        http = resources.runtime.http
        scheduler = Scheduler(settings, restarted.sessions, broker)
        assert await scheduler.dispatch(utc_now()) == 0
        # Advance the dispatch clock past the persisted lease, without waiting.
        later = utc_now() + timedelta(seconds=settings.delivery_lease_seconds + 1)
        assert await scheduler.dispatch(later) == 1
        await asyncio.to_thread(broker.join, "punches", timeout=5000)
        async with restarted.sessions() as session:
            punch = await session.get(Punch, punch_id)
            assert punch is not None
            assert (punch.status, punch.done) == ("done", True)
        assert len(submitted) == 1
    finally:
        await asyncio.to_thread(worker.stop, timeout=5000)
        broker.close()
        await restarted.close()
    assert resources.runtime is None
    assert http.is_closed


@pytest.mark.parametrize("command", ["serve", "worker"])
async def test_cli_processes_jobs_and_stops_on_sigterm(sqlite, local_api: LocalAPI, command: str) -> None:  # noqa: F811
    settings, database = sqlite
    punch_id = await seed(database, settings)
    environment = {
        **os.environ,
        "PM_DATABASE_URL": settings.database_url.get_secret_value(),
        "PM_USER__EMAIL": settings.user.email,
        "PM_USER__PASSWORD": settings.user.password.get_secret_value(),
        "PM_API_URL": local_api.url,
        "PM_POLL_INTERVAL_SECONDS": "0.05",
        "PM_WORKER_THREADS": "2",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "pontomaisoumenos",
        command,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await asyncio.wait_for(local_api.started.wait(), timeout=10)
        async with asyncio.timeout(5):
            while True:
                async with database.sessions() as session:
                    punch = await session.get(Punch, punch_id)
                    if punch is not None and punch.status == "done":
                        break
                await asyncio.sleep(0.05)
        process.send_signal(signal.SIGTERM)
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        assert process.returncode == 0, stderr.decode()
        assert local_api.submissions == 1
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_memory_delayed_retries_keep_the_retry_bound(sqlite, monkeypatch) -> None:
    settings, database = sqlite
    punch_id = await seed(database, settings)
    submissions = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submissions += 1
        return httpx.Response(429)

    monkeypatch.setattr(
        "pontomaisoumenos.worker.Runtime",
        lambda configuration: Runtime(configuration, transport=httpx.MockTransport(handle)),
    )
    broker = configure_broker(settings)
    assert isinstance(broker, MemoryBroker)
    actor = broker.get_actor("register_punch")
    actor.options.update(min_backoff=1, max_backoff=1)
    worker = Worker(broker, worker_threads=2, worker_timeout=10)
    try:
        await asyncio.to_thread(worker.start)
        actor.send(punch_id)
        await asyncio.to_thread(broker.join, "punches", timeout=5000, fail_fast=False)
        assert submissions == 6
    finally:
        await asyncio.to_thread(worker.stop, timeout=5000)
        broker.close()
