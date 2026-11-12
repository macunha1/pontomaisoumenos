"""Resources owned by one worker process and its single asyncio loop."""

import httpx

from .database import Database
from .pontomais import PontoMais
from .processing import PunchProcessor
from .settings import Settings


class Runtime:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.database = Database(settings)
        self.http = httpx.AsyncClient(
            base_url=settings.api_url,
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            limits=httpx.Limits(
                max_connections=settings.http_max_connections,
                max_keepalive_connections=settings.http_max_connections,
            ),
            follow_redirects=False,
            transport=transport,
        )
        self.processor = PunchProcessor(settings, self.database.sessions, PontoMais(settings, self.http))

    async def close(self) -> None:
        try:
            await self.http.aclose()
        finally:
            await self.database.close()
