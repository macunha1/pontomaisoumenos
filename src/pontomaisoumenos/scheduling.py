"""SQL owns durable jobs; brokers only carry near-term delivery IDs."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from dramatiq.broker import Broker
from dramatiq.message import Message
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .database import Punch, User, utc_now
from .processing import aware
from .punches import PunchSimulator
from .settings import Settings

logger = logging.getLogger(__name__)


def generate_month(settings: Settings, local: datetime) -> list[datetime]:
    hours = settings.working_hours
    return PunchSimulator(
        start_min=hours.possible_minutes_variation_start,
        stop_min=hours.possible_minutes_variation_end,
        start_hours=hours.possible_start_hour,
        start_hours_variation=hours.accepted_start_hour_variation,
        expected_daily_hours=hours.expected_daily_hours,
        max_daily_hours=hours.maximum_daily_working_hours,
        lunch_time=hours.lunch_time,
        target_month=local.month,
        target_year=local.year,
        timezone=settings.timezone,
        holiday_subdivision=settings.holiday_subdivision,
        enabled_optional_holidays=settings.enabled_optional_holidays,
    ).generate()


class Scheduler:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession], broker: Broker) -> None:
        self.settings = settings
        self.sessions = sessions
        self.broker = broker

    async def ensure_month(self, now: datetime) -> None:
        local = now.astimezone(self.settings.zone)
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=32)).replace(day=1)
        async with self.sessions.begin() as session:
            insert = sqlite_insert if session.get_bind().dialect.name == "sqlite" else pg_insert
            await session.execute(
                insert(User).values(email=self.settings.user.email).on_conflict_do_nothing(index_elements=["email"])
            )
            # Acquire a write lock before reading the month (SQLite has no FOR UPDATE).
            user = await session.scalar(
                update(User)
                .where(User.email == self.settings.user.email, User.active.is_(True))
                .values(updated_at=now)
                .returning(User)
            )
            if user is None:
                return
            existing = await session.scalar(
                select(Punch.id)
                .where(Punch.user_id == user.id, Punch.should_punch_at >= start, Punch.should_punch_at < end)
                .limit(1)
            )
            if existing is not None:
                return
            # CPU generation must not block broker/resource coroutines.
            generated = await asyncio.to_thread(generate_month, self.settings, local)
            session.add_all(
                Punch(user_id=user.id, should_punch_at=at.astimezone(UTC), status="pending", done=False)
                for at in generated
            )
            logger.info("Created schedule for %s-%02d", local.year, local.month)

    async def dispatch(self, now: datetime) -> int:
        lease = now - timedelta(seconds=self.settings.delivery_lease_seconds)
        earliest = now - timedelta(seconds=self.settings.max_lateness_seconds)
        horizon = now + timedelta(seconds=self.settings.dispatch_horizon_seconds)
        async with self.sessions.begin() as session:
            # A crashed process can leave a claimed submission. Never repeat an
            # external side effect whose outcome cannot be established locally.
            stale_claims = list(
                await session.scalars(
                    update(Punch)
                    .where(Punch.status == "submitting", Punch.updated_at < lease)
                    .values(status="uncertain", updated_at=now)
                    .returning(Punch.id)
                )
            )
            if stale_claims:
                logger.error("%d abandoned submissions require reconciliation", len(stale_claims))
            await session.execute(
                update(Punch)
                .where(Punch.status == "pending", Punch.should_punch_at < earliest)
                .values(status="failed", updated_at=now)
            )
            candidates = (
                select(Punch.id)
                .join(User, User.id == Punch.user_id)
                .where(
                    User.email == self.settings.user.email,
                    User.active.is_(True),
                    Punch.status == "pending",
                    Punch.done.is_(False),
                    Punch.should_punch_at >= earliest,
                    Punch.should_punch_at <= horizon,
                    or_(Punch.queued_at.is_(None), Punch.queued_at < lease),
                )
                .order_by(Punch.should_punch_at)
                .limit(self.settings.dispatch_batch_size)
                .with_for_update(skip_locked=True, of=Punch)
            )
            punches = list(
                await session.scalars(
                    update(Punch).where(Punch.id.in_(candidates)).values(queued_at=now).returning(Punch)
                )
            )
        # No synchronous broker IO on the event loop. A failed publish leaves a
        # bounded lease; a later tick recovers both it and any unsent IDs.
        for punch in punches:
            delay = max(0, round((aware(punch.should_punch_at) - now).total_seconds() * 1000))
            message = Message(
                queue_name="punches", actor_name="register_punch", args=(punch.id,), kwargs={}, options={}
            )
            await asyncio.to_thread(self.broker.enqueue, message, delay=delay)
        return len(punches)

    async def run(self, stop: asyncio.Event, *, generate: bool = True, dispatch: bool = True) -> None:
        while not stop.is_set():
            try:
                now = utc_now()
                if generate:
                    await self.ensure_month(now)
                if dispatch:
                    await self.dispatch(now)
            except Exception as error:
                # Do not emit SQL parameters, URLs, or credentials in error logs.
                logger.error("Scheduler tick failed (%s); retrying next tick", type(error).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.settings.poll_interval_seconds)
            except TimeoutError:
                pass
