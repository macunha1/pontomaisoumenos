"""Measure schedule generation locally; no broker or external API calls."""

import argparse
import json
import platform
from random import Random
from statistics import median
from time import perf_counter

from pontomaisoumenos.punches import PunchSimulator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=100)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("iterations must be positive")
    samples = []
    for index in range(args.iterations):
        start = perf_counter()
        simulator = PunchSimulator(
            start_hours=9,
            start_hours_variation=1.23,
            expected_daily_hours=8.8,
            max_daily_hours=10,
            target_month=index % 12 + 1,
            target_year=2026,
            rng=Random(index),
        )
        simulator.generate()
        samples.append((perf_counter() - start) * 1000)
    samples.sort()
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "iterations": args.iterations,
                "generation_p50_ms": round(median(samples), 3),
                "generation_p95_ms": round(samples[min(len(samples) - 1, int(len(samples) * 0.95))], 3),
            }
        )
    )


if __name__ == "__main__":
    main()
