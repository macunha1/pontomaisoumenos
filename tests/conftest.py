import os
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pontomaisoumenos.database import Base
from pontomaisoumenos.settings import Settings, UserCredentials


@pytest.fixture(autouse=True)
def isolate_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in os.environ:
        if key.startswith("PM_") and not key.startswith("PM_TEST_"):
            monkeypatch.delenv(key)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        user=UserCredentials(email="worker@example.com", password=SecretStr("test-password")), timezone="UTC"
    )


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
