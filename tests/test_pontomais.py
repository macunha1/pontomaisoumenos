import asyncio
import json

import httpx
import pytest

from pontomaisoumenos.pontomais import PermanentPunchError, PontoMais, RetryablePunchError, UncertainPunchError
from pontomaisoumenos.settings import Settings


async def test_shared_authentication_and_overlapping_async_requests(settings: Settings) -> None:
    auth_calls = 0
    active = 0
    peak = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls, active, peak
        if request.url.path == "/api/auth/sign_in":
            auth_calls += 1
            return httpx.Response(200, json={"token": "token", "client_id": "client", "expiry": 9999999999})
        assert request.headers["access-token"] == "token"
        assert json.loads(request.content)["time_card"]["latitude"] == 12.5
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "2026-01-01T09:00:00Z"}})

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        api = PontoMais(settings, http)
        await asyncio.gather(api.authenticate(), api.authenticate())
        await asyncio.gather(api.register_punch("Office", 12.5, 20), api.register_punch("Office", 12.5, 20))
    assert auth_calls == 1
    assert peak == 2


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, RetryablePunchError), (429, RetryablePunchError), (403, PermanentPunchError), (503, UncertainPunchError)],
)
async def test_submission_status_classification(settings: Settings, status: int, expected: type[Exception]) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        return httpx.Response(status)

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        api = PontoMais(settings, http)
        await api.authenticate()
        with pytest.raises(expected):
            await api.register_punch("Office", 0, 0)
        if status == 401:
            assert api.authentication is None


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (httpx.ConnectError, RetryablePunchError),
        (httpx.ConnectTimeout, RetryablePunchError),
        (httpx.PoolTimeout, RetryablePunchError),
        (httpx.ReadTimeout, UncertainPunchError),
        (httpx.WriteError, UncertainPunchError),
    ],
)
async def test_transport_failure_classification(
    settings: Settings, failure: type[httpx.TransportError], expected: type[Exception]
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        raise failure("test failure")

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        api = PontoMais(settings, http)
        await api.authenticate()
        with pytest.raises(expected):
            await api.register_punch("Office", 0, 0)


async def test_unverifiable_success_is_uncertain(settings: Settings) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("sign_in"):
            return httpx.Response(200, json={"token": "t", "client_id": "c", "expiry": "e"})
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        api = PontoMais(settings, http)
        await api.authenticate()
        with pytest.raises(UncertainPunchError):
            await api.register_punch("Office", 0, 0)


async def test_token_invalidated_between_claim_and_submission_refreshes(settings: Settings) -> None:
    auth_calls = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal auth_calls
        if request.url.path.endswith("sign_in"):
            auth_calls += 1
            return httpx.Response(200, json={"token": f"token-{auth_calls}", "client_id": "c", "expiry": "e"})
        assert request.headers["access-token"] == "token-2"
        return httpx.Response(200, json={"untreated_time_card": {"created_at": "now"}})

    async with httpx.AsyncClient(base_url=settings.api_url, transport=httpx.MockTransport(handle)) as http:
        api = PontoMais(settings, http)
        await api.authenticate()
        # An overlapping job can receive a 401 while this job's claim commits.
        api.authentication = None
        await api.register_punch("Office", 0, 0)
    assert auth_calls == 2
