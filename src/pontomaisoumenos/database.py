"""Typed persistence and explicit async engine ownership."""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, event, make_url
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .settings import Settings

type PunchStatus = Literal["pending", "submitting", "done", "uncertain", "failed"]


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "USERS"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(128), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Punch(Base):
    __tablename__ = "WORKING_PUNCHES"
    __table_args__ = (
        UniqueConstraint("user_id", "should_punch_at", name="uq_punch_user_time"),
        Index("ix_punch_dispatch", "status", "should_punch_at", "queued_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("USERS.id", ondelete="CASCADE"))
    should_punch_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[PunchStatus] = mapped_column(String(16), default="pending")
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Database:
    def __init__(self, settings: Settings) -> None:
        url = make_url(settings.database_url.get_secret_value())
        sqlite = url.get_backend_name() == "sqlite"
        pool_options = (
            {}
            if sqlite and url.database in {None, "", ":memory:"}
            else {
                "pool_size": settings.database_pool_size,
                "max_overflow": 0,
                "pool_timeout": 10,
            }
        )
        self.engine: AsyncEngine = create_async_engine(
            url,
            connect_args={"timeout": 10} if sqlite else {"connect_timeout": 10},
            pool_pre_ping=True,
            **pool_options,
        )
        if sqlite:
            event.listen(self.engine.sync_engine, "connect", configure_sqlite)
        self.sessions: async_sessionmaker[AsyncSession] = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()


def configure_sqlite(connection: DBAPIConnection, record: object) -> None:
    """Enable concurrent readers, bounded lock waits, and foreign key checks."""
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()
        if mode is not None and mode[0] != "wal":
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
