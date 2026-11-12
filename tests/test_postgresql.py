"""Real row locking, legacy migration, and Redis worker lifecycle contracts."""

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from importlib.resources import as_file, files
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from dramatiq import Worker
from pydantic import SecretStr
from sqlalchemy import make_url, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from pontomaisoumenos.cli import migrate
from pontomaisoumenos.database import Base, Punch, User, utc_now
from pontomaisoumenos.pontomais import PontoMais
from pontomaisoumenos.processing import PunchProcessor
from pontomaisoumenos.runtime import Runtime
from pontomaisoumenos.scheduling import Scheduler
from pontomaisoumenos.settings import Settings
from pontomaisoumenos.worker import WorkerResources, configure_broker

from .test_scheduling import RecordingBroker

pytestmark = [
    pytest.mark.postgresql,
    pytest.mark.skipif(not os.getenv("PM_TEST_DATABASE_URL"), reason="No test PostgreSQL"),
]


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    url = make_url(os.environ["PM_TEST_DATABASE_URL"])
    admin = create_async_engine(url)
    schema = f"test_{uuid4().hex}"
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(url.update_query_dict({"options": f"-csearch_path={schema}"}))
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def seed(engine: AsyncEngine, settings: Settings) -> str:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False).begin() as session:
        user = User(email=settings.user.email)
        session.add(user)
        await session.flush()
        punch = Punch(user_id=user.id, should_punch_at=utc_now() - timedelta(seconds=1))
        session.add(punch)
        await session.flush()
        return punch.id


async def test_concurrent_delivery_submits_once(pg_engine: AsyncEngine, settings: Settings) -> None:
    punch_id = await seed(pg_engine, settings)
    submissions = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submissions += 1
        await asyncio.sleep(0.03)
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        sessions = async_sessionmaker(pg_engine, expire_on_commit=False)
        processor = PunchProcessor(settings, sessions, PontoMais(settings, http))
        await asyncio.gather(processor.process(punch_id), processor.process(punch_id))
    assert submissions == 1
    async with pg_engine.connect() as connection:
        assert (await connection.execute(select(Punch.status))).scalar_one() == "done"


async def test_concurrent_schedulers_claim_once(pg_engine: AsyncEngine, settings: Settings) -> None:
    await seed(pg_engine, settings)
    broker = RecordingBroker()
    sessions = async_sessionmaker(pg_engine, expire_on_commit=False)
    first = Scheduler(settings, sessions, broker)
    second = Scheduler(settings, sessions, broker)
    await asyncio.gather(first.dispatch(utc_now()), second.dispatch(utc_now()))
    assert len(broker.messages) == 1


async def test_legacy_migration_converts_timezone_and_preserves_rows(pg_engine: AsyncEngine) -> None:
    url = pg_engine.url.render_as_string(hide_password=False)
    with as_file(files("pontomaisoumenos").joinpath("migrations")) as directory:
        config = Config()
        config.set_main_option("script_location", str(directory))
        config.attributes["database_url"] = url
        await asyncio.to_thread(command.upgrade, config, "0001")
    async with pg_engine.begin() as connection:
        await connection.execute(text("INSERT INTO \"USERS\" (id, email, active) VALUES ('u', 'u@example.com', true)"))
        await connection.execute(
            text(
                'INSERT INTO "WORKING_PUNCHES" (id, user_id, should_punch_at, done) '
                "VALUES ('p', 'u', '2026-01-10 09:00:00', true)"
            )
        )
    settings = Settings(database_url=SecretStr(url), timezone="America/Sao_Paulo")
    await asyncio.to_thread(migrate, settings)
    async with pg_engine.connect() as connection:
        row = (await connection.execute(select(Punch.should_punch_at, Punch.status))).one()
        assert row.should_punch_at == datetime(2026, 1, 10, 12, tzinfo=UTC)
        assert row.status == "done"


@pytest.mark.skipif(not os.getenv("PM_TEST_REDIS_URL"), reason="No test Redis")
async def test_real_redis_async_worker_lifecycle(
    pg_engine: AsyncEngine, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    punch_id = await seed(pg_engine, settings)
    settings = settings.model_copy(
        update={
            "database_url": SecretStr(pg_engine.url.render_as_string(hide_password=False)),
            "broker": "redis",
            "redis_url": SecretStr(os.environ["PM_TEST_REDIS_URL"]),
            "redis_namespace": f"test-{uuid4().hex}",
        }
    )

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    def runtime_factory(configuration: Settings) -> Runtime:
        return Runtime(configuration, transport=httpx.MockTransport(handle))

    monkeypatch.setattr("pontomaisoumenos.worker.Runtime", runtime_factory)
    broker = configure_broker(settings)
    worker = Worker(broker, worker_threads=2, worker_timeout=100)
    resources = next(item for item in broker.middleware if isinstance(item, WorkerResources))
    try:
        await asyncio.to_thread(worker.start)
        assert resources.runtime is not None
        http = resources.runtime.http
        await asyncio.to_thread(broker.get_actor("register_punch").send, punch_id)
        await asyncio.to_thread(broker.join, "punches", timeout=5000)
        async with pg_engine.connect() as connection:
            assert (await connection.execute(select(Punch.status))).scalar_one() == "done"
    finally:
        await asyncio.to_thread(worker.stop, timeout=5000)
        await asyncio.to_thread(broker.flush_all)
        await asyncio.to_thread(broker.close)
    assert resources.runtime is None
    assert http.is_closed
