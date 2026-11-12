import asyncio
from datetime import timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pontomaisoumenos.database import Punch, User, utc_now
from pontomaisoumenos.pontomais import PontoMais, RetryablePunchError
from pontomaisoumenos.processing import PunchProcessor
from pontomaisoumenos.settings import Settings


async def seed_punch(sessions: async_sessionmaker[AsyncSession], settings: Settings, **changes: object) -> str:
    async with sessions.begin() as session:
        user = User(email=settings.user.email, active=True)
        session.add(user)
        await session.flush()
        attributes = {"user_id": user.id, "should_punch_at": utc_now() - timedelta(seconds=1), **changes}
        punch = Punch(**attributes)
        session.add(punch)
        await session.flush()
        return punch.id


async def get_status(sessions: async_sessionmaker[AsyncSession], punch_id: str) -> tuple[str, bool]:
    async with sessions() as session:
        punch = await session.get(Punch, punch_id)
        assert punch is not None
        return punch.status, punch.done


async def test_success_and_duplicate_delivery(sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
    punch_id = await seed_punch(sessions, settings)
    submissions = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submissions += 1
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        processor = PunchProcessor(settings, sessions, PontoMais(settings, http))
        await processor.process(punch_id)
        await processor.process(punch_id)
    assert submissions == 1
    assert await get_status(sessions, punch_id) == ("done", True)


@pytest.mark.parametrize(("failure", "outcome"), [(httpx.ReadTimeout, "uncertain"), (httpx.ConnectError, "pending")])
async def test_durable_transport_outcomes(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, failure: type[httpx.TransportError], outcome: str
) -> None:
    punch_id = await seed_punch(sessions, settings)
    submissions = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal submissions
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submissions += 1
        raise failure("test failure")

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        processor = PunchProcessor(settings, sessions, PontoMais(settings, http))
        if outcome == "pending":
            with pytest.raises(RetryablePunchError):
                await processor.process(punch_id)
        else:
            await processor.process(punch_id)
            await processor.process(punch_id)
    assert submissions == 1
    assert await get_status(sessions, punch_id) == (outcome, False)


@pytest.mark.parametrize(("offset", "outcome"), [(60, "pending"), (-1000, "failed")])
async def test_never_submits_early_or_expired_work(
    sessions: async_sessionmaker[AsyncSession], settings: Settings, offset: int, outcome: str
) -> None:
    punch_id = await seed_punch(sessions, settings, should_punch_at=utc_now() + timedelta(seconds=offset))

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("This job must not call the API")

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        await PunchProcessor(settings, sessions, PontoMais(settings, http)).process(punch_id)
    assert await get_status(sessions, punch_id) == (outcome, False)


async def test_cancellation_after_claim_never_resubmits(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    punch_id = await seed_punch(sessions, settings)
    submitting = asyncio.Event()

    async def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        submitting.set()
        await asyncio.Event().wait()
        raise AssertionError("Cancelled submission must not finish")

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        processor = PunchProcessor(settings, sessions, PontoMais(settings, http))
        task = asyncio.create_task(processor.process(punch_id))
        await asyncio.wait_for(submitting.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await get_status(sessions, punch_id) == ("submitting", False)
        await processor.process(punch_id)


async def test_delivery_does_not_change_another_accounts_job(
    sessions: async_sessionmaker[AsyncSession], settings: Settings
) -> None:
    punch_id = await seed_punch(sessions, settings)
    other = settings.model_copy(update={"user": settings.user.model_copy(update={"email": "other@example.com"})})

    def handle(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Another account's delivery must not call the API")

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        await PunchProcessor(other, sessions, PontoMais(other, http)).process(punch_id)
    assert await get_status(sessions, punch_id) == ("pending", False)
