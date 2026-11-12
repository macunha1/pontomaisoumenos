"""Alembic environment using the application's explicitly supplied connection URL."""

import asyncio

from alembic import context
from sqlalchemy import Connection, event, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from pontomaisoumenos.database import Base, configure_sqlite


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(context.config.attributes["database_url"], poolclass=NullPool)
    if make_url(context.config.attributes["database_url"]).get_backend_name() == "sqlite":
        event.listen(engine.sync_engine, "connect", configure_sqlite)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=context.config.attributes["database_url"], target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
