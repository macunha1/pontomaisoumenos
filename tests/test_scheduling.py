from datetime import UTC, date, datetime, timedelta

import pytest
from dramatiq.brokers.stub import StubBroker
from dramatiq.message import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pontomaisoumenos.database import Punch, User
from pontomaisoumenos.holidays import OptionalHoliday
from pontomaisoumenos.scheduling import Scheduler
from pontomaisoumenos.settings import Settings


class RecordingBroker(StubBroker):
    def __init__(self) -> None:
        super().__init__()
        self.messages: list[tuple[Message, int | None]] = []
        self.fail = False

    def enqueue(self, message: Message, *, delay: int | None = None) -> Message:
        if self.fail:
            raise ConnectionError("Redis unavailable")
        self.messages.append((message, delay))
        return message


@pytest.mark.parametrize("enabled", [(), ("carnival",), ("carnival", "ash_wednesday")])
async def test_optional_holidays_control_persisted_punches_without_replacing_existing_month(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, enabled: tuple[OptionalHoliday, ...]
) -> None:
    settings.enabled_optional_holidays = enabled
    scheduler = Scheduler(settings, sessions, RecordingBroker())
    february = datetime(2026, 2, 1, 12, tzinfo=UTC)
    await scheduler.ensure_month(february)
    async with sessions() as session:
        punches = list(await session.scalars(select(Punch)))
        first_ids = {punch.id for punch in punches}
        days = {punch.should_punch_at.date() for punch in punches}
    assert (date(2026, 2, 16) in days) == ("carnival" not in enabled)
    assert (date(2026, 2, 17) in days) == ("carnival" not in enabled)
    assert (date(2026, 2, 18) in days) == ("ash_wednesday" not in enabled)
    assert date(2026, 2, 19) in days

    settings.enabled_optional_holidays = () if enabled else ("carnival",)
    await scheduler.ensure_month(february)
    async with sessions() as session:
        assert set(await session.scalars(select(Punch.id))) == first_ids


async def test_month_rollover_and_idempotent_generation(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    scheduler = Scheduler(settings, sessions, RecordingBroker())
    january = datetime(2026, 1, 15, tzinfo=UTC)
    await scheduler.ensure_month(january)
    async with sessions() as session:
        first_ids = set(await session.scalars(select(Punch.id)))
    await scheduler.ensure_month(january)
    async with sessions() as session:
        assert set(await session.scalars(select(Punch.id))) == first_ids
    await scheduler.ensure_month(datetime(2026, 2, 1, tzinfo=UTC))
    async with sessions() as session:
        assert len(list(await session.scalars(select(Punch.id)))) > len(first_ids)


async def test_dispatch_only_near_term_pending_ids_and_recover_lost_messages(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    now = datetime(2026, 1, 15, 10, tzinfo=UTC)
    async with sessions.begin() as session:
        user = User(email=settings.user.email)
        session.add(user)
        await session.flush()
        for status, minutes in [("pending", 0), ("pending", 1), ("pending", 60), ("done", 0), ("submitting", 0)]:
            session.add(
                Punch(
                    user_id=user.id,
                    should_punch_at=now + timedelta(minutes=minutes, seconds=len(session.new)),
                    status=status,
                    done=status == "done",
                    updated_at=now - timedelta(hours=1),
                )
            )
    broker = RecordingBroker()
    scheduler = Scheduler(settings, sessions, broker)
    assert await scheduler.dispatch(now) == 1
    message, delay = broker.messages[0]
    assert message.actor_name == "register_punch"
    assert len(message.args) == 1
    assert message.kwargs == {}
    assert "password" not in message.encode().decode()
    assert delay == 0
    assert await scheduler.dispatch(now) == 0
    assert await scheduler.dispatch(now + timedelta(seconds=settings.delivery_lease_seconds + 1)) == 2
    async with sessions() as session:
        assert await session.scalar(select(Punch.id).where(Punch.status == "uncertain")) is not None


async def test_broker_failure_recovers_after_lease(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    now = datetime(2026, 1, 15, 10, tzinfo=UTC)
    async with sessions.begin() as session:
        user = User(email=settings.user.email)
        session.add(user)
        await session.flush()
        session.add(Punch(user_id=user.id, should_punch_at=now))
    broker = RecordingBroker()
    broker.fail = True
    scheduler = Scheduler(settings, sessions, broker)
    try:
        await scheduler.dispatch(now)
    except ConnectionError:
        pass
    else:
        raise AssertionError("Publishing should fail")
    broker.fail = False
    assert await scheduler.dispatch(now) == 0
    assert await scheduler.dispatch(now + timedelta(seconds=settings.delivery_lease_seconds + 1)) == 1
