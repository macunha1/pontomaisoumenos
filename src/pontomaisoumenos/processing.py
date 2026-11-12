"""Durable delivery state around the external side effect."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .database import Punch, PunchStatus, User, utc_now
from .gps import GpsOscilator
from .pontomais import PermanentPunchError, PontoMais, RetryablePunchError, UncertainPunchError
from .settings import Settings

logger = logging.getLogger(__name__)


def aware(value: datetime) -> datetime:
    """SQLite stores naive UTC values; PostgreSQL returns aware UTC values."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class PunchProcessor:
    def __init__(self, settings: Settings, sessions: async_sessionmaker[AsyncSession], api: PontoMais) -> None:
        self.settings = settings
        self.sessions = sessions
        self.api = api
        self.gps = GpsOscilator(settings.location.latitude, settings.location.longitude)

    async def process(self, punch_id: str) -> None:
        async with self.sessions.begin() as session:
            # Claim before reading or changing delivery state. SQLite ignores
            # FOR UPDATE, so even expiry and early-delivery handling need ownership.
            punch = await session.scalar(
                update(Punch)
                .where(
                    Punch.id == punch_id,
                    Punch.status == "pending",
                    Punch.done.is_(False),
                    Punch.user_id.in_(select(User.id).where(User.email == self.settings.user.email)),
                )
                .values(status="submitting", updated_at=utc_now())
                .returning(Punch)
            )
            if punch is None:
                return
            user = await session.get(User, punch.user_id)
            if user is None or not user.active or user.email != self.settings.user.email:
                punch.status = "failed"
                punch.updated_at = utc_now()
                return
            now = utc_now()
            scheduled_at = aware(punch.should_punch_at)
            if scheduled_at > now:
                # A clock skew or early delivery must not submit before the schedule.
                punch.status = "pending"
                punch.queued_at = None
                return
            if scheduled_at < now - timedelta(seconds=self.settings.max_lateness_seconds):
                punch.status = "failed"
                punch.updated_at = now
                logger.warning("Punch %s expired before submission", punch_id)
                return
        # Commit before network IO so redelivery cannot repeat an external effect.
        try:
            await self.api.authenticate()
        except RetryablePunchError:
            await self.set_outcome(punch_id, "pending")
            raise
        except PermanentPunchError:
            await self.set_outcome(punch_id, "failed")
            logger.error("Punch %s authentication rejected", punch_id)
            return

        latitude, longitude = self.gps.generate_latlong()
        try:
            await self.api.register_punch(self.settings.location.address, latitude, longitude)
        except RetryablePunchError:
            await self.set_outcome(punch_id, "pending")
            raise
        except PermanentPunchError:
            await self.set_outcome(punch_id, "failed")
            logger.error("Punch %s rejected by the API", punch_id)
        except UncertainPunchError:
            await self.set_outcome(punch_id, "uncertain")
            logger.error("Punch %s needs reconciliation; remote outcome is unknown", punch_id)
        else:
            await self.set_outcome(punch_id, "done")
            logger.info("Punch %s completed", punch_id)

    async def set_outcome(self, punch_id: str, status: PunchStatus) -> None:
        async with self.sessions.begin() as session:
            punch = await session.get(Punch, punch_id, with_for_update=True)
            if punch is not None:
                punch.status = status
                punch.done = status == "done"
                punch.updated_at = utc_now()
                # Keep the dispatch lease for transient failures. Broker retries
                # run first; the scheduler recovers work after a lost message.
