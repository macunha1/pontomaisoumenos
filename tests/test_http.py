"""Exercise real HTTP pooling, timeouts, retries, and cancellation on loopback."""

import asyncio
import json
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pontomaisoumenos.pontomais import RetryablePunchError, UncertainPunchError
from pontomaisoumenos.processing import PunchProcessor
from pontomaisoumenos.runtime import Runtime
from pontomaisoumenos.settings import Settings

from .test_processing import get_status, seed_punch


@dataclass
class LocalAPI:
    url: str = ""
    connections: int = 0
    authentications: int = 0
    submissions: int = 0
    active: int = 0
    peak: int = 0
    statuses: deque[int] = field(default_factory=deque)
    started: asyncio.Event = field(default_factory=asyncio.Event)
    saturated: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    writers: set[asyncio.StreamWriter] = field(default_factory=set)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        self.writers.add(writer)
        self.connections += 1
        try:
            while True:
                headers = (await reader.readuntil(b"\r\n\r\n")).decode("ascii")
                lines = headers.split("\r\n")
                method, path, _ = lines[0].split()
                assert method == "POST"
                length = next(
                    int(line.split(":", 1)[1]) for line in lines if line.lower().startswith("content-length:")
                )
                await reader.readexactly(length)
                if path == "/api/auth/sign_in":
                    self.authentications += 1
                    status = 200
                    payload = {"token": "local-token", "client_id": "local-client", "expiry": "9999999999"}
                else:
                    assert path == "/api/time_cards/register"
                    self.submissions += 1
                    self.active += 1
                    self.peak = max(self.peak, self.active)
                    self.started.set()
                    if self.active >= 2:
                        self.saturated.set()
                    try:
                        await self.release.wait()
                        status = self.statuses.popleft() if self.statuses else 200
                        payload = {"untreated_time_card": {"created_at": "2026-11-12T09:00:00Z"}}
                    finally:
                        self.active -= 1
                body = json.dumps(payload).encode()
                writer.write(
                    f"HTTP/1.1 {status} Response\r\nContent-Type: application/json\r\n"
                    f"Content-Length: {len(body)}\r\n\r\n".encode()
                    + body
                )
                await writer.drain()
        except asyncio.IncompleteReadError, ConnectionError:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except ConnectionError:
                pass
            self.writers.discard(writer)
            self.tasks.discard(task)


@pytest.fixture
async def local_api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[LocalAPI]:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    api = LocalAPI()
    api.release.set()
    server = await asyncio.start_server(api.handle, "127.0.0.1", 0)
    api.url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}"
    try:
        yield api
    finally:
        server.close()
        api.release.set()
        for writer in tuple(api.writers):
            writer.close()
        if api.tasks:
            await asyncio.wait_for(asyncio.gather(*api.tasks), timeout=3)
        await asyncio.wait_for(server.wait_closed(), timeout=3)


@pytest.fixture
async def http_runtime(local_api: LocalAPI, settings: Settings) -> AsyncIterator[Runtime]:
    configuration = settings.model_copy(update={"api_url": local_api.url, "http_max_connections": 2})
    runtime = Runtime(configuration)
    try:
        yield runtime
    finally:
        await runtime.close()


async def test_real_pool_reuses_connections_and_bounds_concurrency(local_api: LocalAPI, http_runtime: Runtime) -> None:
    api = http_runtime.processor.api
    await api.authenticate()
    local_api.release.clear()
    tasks = [asyncio.create_task(api.register_punch("Office", 12.5, 20)) for _ in range(6)]
    try:
        await asyncio.wait_for(local_api.saturated.wait(), timeout=3)
        await asyncio.sleep(0.03)
        assert local_api.active == 2
        assert not any(task.done() for task in tasks)
        local_api.release.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
    finally:
        local_api.release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert local_api.peak == 2
    assert local_api.connections == 2
    assert local_api.authentications == 1
    assert local_api.submissions == 6


async def test_real_read_timeout_has_uncertain_outcome(local_api: LocalAPI, http_runtime: Runtime) -> None:
    await http_runtime.processor.api.authenticate()
    http_runtime.http.timeout = httpx.Timeout(0.05)
    local_api.release.clear()
    with pytest.raises(UncertainPunchError, match="outcome is unknown"):
        await http_runtime.processor.api.register_punch("Office", 0, 0)
    assert local_api.submissions == 1


async def test_real_pool_timeout_is_safe_and_cancellation_releases_connection(
    local_api: LocalAPI, settings: Settings
) -> None:
    runtime = Runtime(settings.model_copy(update={"api_url": local_api.url, "http_max_connections": 1}))
    runtime.http.timeout = httpx.Timeout(3, pool=0.05)
    api = runtime.processor.api
    task: asyncio.Task[None] | None = None
    try:
        await api.authenticate()
        local_api.release.clear()
        task = asyncio.create_task(api.register_punch("Office", 0, 0))
        await asyncio.wait_for(local_api.started.wait(), timeout=3)
        with pytest.raises(RetryablePunchError, match="before submission"):
            await api.register_punch("Office", 0, 0)
        assert local_api.submissions == 1
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        local_api.release.set()
        await asyncio.wait_for(api.register_punch("Office", 0, 0), timeout=3)
        assert local_api.submissions == 2
    finally:
        local_api.release.set()
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await runtime.close()
    assert runtime.http.is_closed


@pytest.mark.parametrize(("status", "outcome"), [(429, "done"), (503, "uncertain")])
async def test_real_http_delivery_retries_only_known_rejections(
    local_api: LocalAPI,
    http_runtime: Runtime,
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    status: int,
    outcome: str,
) -> None:
    punch_id = await seed_punch(sessions, settings)
    processor = PunchProcessor(settings, sessions, http_runtime.processor.api)
    local_api.statuses.append(status)
    if status == 429:
        with pytest.raises(RetryablePunchError):
            await processor.process(punch_id)
        assert await get_status(sessions, punch_id) == ("pending", False)
    else:
        await processor.process(punch_id)
    await processor.process(punch_id)
    await processor.process(punch_id)
    assert await get_status(sessions, punch_id) == (outcome, outcome == "done")
    assert local_api.submissions == (2 if status == 429 else 1)
    assert local_api.authentications == 1
    assert local_api.connections == 1
