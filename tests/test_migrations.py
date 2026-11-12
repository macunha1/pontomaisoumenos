import asyncio
from importlib.resources import as_file, files
from pathlib import Path

from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from pontomaisoumenos.cli import migrate
from pontomaisoumenos.settings import Settings


async def test_packaged_migrations_upgrade_existing_rows(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}"
    with as_file(files("pontomaisoumenos").joinpath("migrations")) as directory:
        config = Config()
        config.set_main_option("script_location", str(directory))
        config.attributes["database_url"] = url
        await asyncio.to_thread(command.upgrade, config, "0001")
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.execute(text("INSERT INTO \"USERS\" (id, email) VALUES ('u', 'u@example.com')"))
        await connection.execute(
            text(
                'INSERT INTO "WORKING_PUNCHES" (id, user_id, should_punch_at, done) '
                "VALUES ('p', 'u', '2026-01-01 09:00:00', true)"
            )
        )
    await engine.dispose()
    settings = Settings(database_url=SecretStr(url))
    await asyncio.to_thread(migrate, settings)
    await asyncio.to_thread(migrate, settings)
    async with engine.connect() as connection:
        assert (await connection.execute(text('SELECT status FROM "WORKING_PUNCHES"'))).scalar_one() == "done"
        columns = await connection.run_sync(lambda conn: inspect(conn).get_columns("WORKING_PUNCHES"))
        assert {"queued_at", "status"} <= {column["name"] for column in columns}
    await engine.dispose()
