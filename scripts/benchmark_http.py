"""Compare sequential and bounded async submissions against a loopback API.

This measures overlapping simulated network waits, not production API capacity.
The server, credentials, and endpoint are local fixtures; no real account is used.
"""

import argparse
import asyncio
import json
import platform
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from statistics import median
from typing import cast

import httpx
from pydantic import SecretStr

from pontomaisoumenos.pontomais import PontoMais
from pontomaisoumenos.settings import Settings, UserCredentials


@dataclass
class RequestCounts:
    active: int = 0
    peak: int = 0
    submissions: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def reset(self) -> None:
        with self.lock:
            if self.active:
                raise RuntimeError("Previous sample still has active requests")
            self.peak = 0
            self.submissions = 0


class SimulatedAPI(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, latency_seconds: float) -> None:
        self.latency_seconds = latency_seconds
        self.counts = RequestCounts()
        super().__init__(("127.0.0.1", 0), APIHandler)


class APIHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    disable_nagle_algorithm = True

    def do_POST(self) -> None:
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/api/auth/sign_in":
            response = {"token": "local-token", "client_id": "local-client", "expiry": "9999999999"}
        elif self.path == "/api/time_cards/register":
            server = cast(SimulatedAPI, self.server)
            with server.counts.lock:
                server.counts.active += 1
                server.counts.peak = max(server.counts.peak, server.counts.active)
                server.counts.submissions += 1
            try:
                time.sleep(server.latency_seconds)
                response = {"untreated_time_card": {"created_at": "2026-11-12T09:00:00Z"}}
            finally:
                with server.counts.lock:
                    server.counts.active -= 1
        else:
            self.send_error(404)
            return
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        pass


@dataclass(frozen=True)
class Sample:
    seconds: float
    peak_requests: int


async def measure(server: SimulatedAPI, jobs: int, workers: int) -> Sample:
    server.counts.reset()
    # Internal fixture: do not read PM_ environment variables or real credentials.
    settings = Settings.model_construct(
        user=UserCredentials(email="benchmark@example.invalid", password=SecretStr("local-only"))
    )
    url = f"http://127.0.0.1:{server.server_port}"
    async with httpx.AsyncClient(
        base_url=url,
        timeout=httpx.Timeout(max(5, server.latency_seconds * 3)),
        limits=httpx.Limits(max_connections=workers, max_keepalive_connections=workers),
        trust_env=False,
    ) as http:
        api = PontoMais(settings, http)
        await api.authenticate()
        pending = iter(range(jobs))

        async def consume() -> None:
            for _ in pending:
                await api.register_punch("Local benchmark", 0, 0)

        started = time.perf_counter()
        async with asyncio.TaskGroup() as group:
            for _ in range(min(workers, jobs)):
                group.create_task(consume())
        elapsed = time.perf_counter() - started
    if server.counts.submissions != jobs:
        raise RuntimeError("Benchmark did not process the requested number of jobs")
    return Sample(elapsed, server.counts.peak)


async def compare(server: SimulatedAPI, jobs: int, workers: int, iterations: int) -> dict[str, object]:
    sequential: list[Sample] = []
    concurrent: list[Sample] = []
    for index in range(iterations):
        # Alternate order to reduce systematic warmup bias.
        order = ((1, sequential), (workers, concurrent))
        for concurrency, samples in order if index % 2 == 0 else reversed(order):
            samples.append(await measure(server, jobs, concurrency))
    sequential_seconds = median(sample.seconds for sample in sequential)
    concurrent_seconds = median(sample.seconds for sample in concurrent)
    return {
        "scenario": "loopback HTTP with simulated latency; not production throughput",
        "python": platform.python_version(),
        "jobs_per_sample": jobs,
        "workers": workers,
        "iterations": iterations,
        "simulated_latency_ms": round(server.latency_seconds * 1000, 3),
        "sequential_median_seconds": round(sequential_seconds, 4),
        "concurrent_median_seconds": round(concurrent_seconds, 4),
        "speedup": round(sequential_seconds / concurrent_seconds, 2),
        "peak_concurrent_requests": max(sample.peak_requests for sample in concurrent),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=int, default=32)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--latency-ms", type=float, default=50)
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    if args.jobs < 1 or not 1 <= args.workers <= 64 or args.iterations < 1 or not 0 <= args.latency_ms <= 1000:
        parser.error("jobs/iterations must be positive, workers within 1..64, and latency within 0..1000 ms")
    server = SimulatedAPI(args.latency_ms / 1000)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        print(json.dumps(asyncio.run(compare(server, args.jobs, args.workers, args.iterations))))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
