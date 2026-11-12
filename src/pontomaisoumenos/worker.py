"""Explicit Dramatiq broker composition, with no import-time connections."""

import asyncio
import logging
import os
from pathlib import Path

import dramatiq
from dramatiq.asyncio import get_event_loop_thread
from dramatiq.broker import Broker
from dramatiq.middleware import AsyncIO

from .broker import MemoryBroker
from .pontomais import RetryablePunchError
from .runtime import Runtime
from .settings import Settings, load_settings


class WorkerResources(AsyncIO):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.runtime: Runtime | None = None

    async def open(self) -> None:
        self.runtime = Runtime(self.settings)

    async def close(self) -> None:
        if self.runtime is not None:
            await self.runtime.close()
            self.runtime = None

    def before_worker_boot(self, broker: Broker, worker: dramatiq.Worker) -> None:
        super().before_worker_boot(broker, worker)
        loop = get_event_loop_thread()
        if loop is None:
            raise RuntimeError("Dramatiq asyncio loop was not started")
        loop.run_coroutine(self.open())

    def after_worker_shutdown(self, broker: Broker, worker: dramatiq.Worker) -> None:
        loop = get_event_loop_thread()
        try:
            if loop is not None:
                loop.run_coroutine(self.close())
        finally:
            super().after_worker_shutdown(broker, worker)


def retry_when(retries: int, exception: BaseException) -> bool:
    return retries < 5 and isinstance(exception, RetryablePunchError)


def configure_broker(settings: Settings, broker: Broker | None = None) -> Broker:
    resources = WorkerResources(settings)
    if broker is None:
        if settings.broker == "memory":
            broker = MemoryBroker()
        else:
            from dramatiq.brokers.redis import RedisBroker

            broker = RedisBroker(
                url=settings.redis_url.get_secret_value(),
                namespace=settings.redis_namespace,
                socket_connect_timeout=5,
                socket_timeout=5,
                socket_keepalive=True,
            )
    broker.add_middleware(resources)

    async def register_punch(punch_id: str) -> None:
        if resources.runtime is None:
            raise RuntimeError("Worker resources have not started")
        # Dramatiq's thread time limits cannot interrupt asyncio IO. Bound the
        # coroutine itself; a cancellation after claiming remains 'submitting'.
        async with asyncio.timeout(settings.http_timeout_seconds * 3):
            await resources.runtime.processor.process(punch_id)

    dramatiq.actor(
        broker=broker,
        actor_name="register_punch",
        queue_name="punches",
        retry_when=retry_when,
        min_backoff=5000,
        max_backoff=60000,
        max_age=settings.max_lateness_seconds * 1000,
    )(register_punch)
    return broker


def boot() -> None:
    """Dramatiq CLI factory, invoked after process startup."""
    config_file = os.environ.get("PM_CONFIG_FILE")
    settings = load_settings(Path(config_file) if config_file else None)
    settings.require_credentials()
    logging.getLogger().setLevel(settings.log_level)
    dramatiq.set_broker(configure_broker(settings))
