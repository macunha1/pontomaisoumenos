from datetime import date, timedelta
from itertools import pairwise
from random import Random

import pytest

from pontomaisoumenos.gps import GpsOscilator
from pontomaisoumenos.holidays import business_days
from pontomaisoumenos.punches import PunchSimulator, ScheduleNotPossible


def test_movable_brazilian_holidays_and_subdivision() -> None:
    assert date(2026, 4, 3) not in business_days(2026, 4)
    assert date(2026, 3, 30) in business_days(2026, 3)
    assert date(2026, 7, 9) not in business_days(2026, 7, "SP")
    assert date(2026, 7, 9) in business_days(2026, 7, "RJ")


def test_static_working_journey_generation() -> None:
    simulator = PunchSimulator(lunch_time=0, target_month=11, target_year=2017)
    punches = simulator.generate()
    assert len(punches) == 2 * len(simulator.get_business_days())
    assert all(end - start == timedelta(hours=8) for start, end in zip(punches[::2], punches[1::2], strict=True))
    assert all(punch.tzinfo is not None for punch in punches)
    assert simulator.convert_timedelta_to_hours(timedelta(hours=100, minutes=20)) == 100


@pytest.mark.parametrize("month", range(1, 13))
def test_fractional_monthly_target_and_daily_bounds(month: int) -> None:
    simulator = PunchSimulator(
        start_hours=9,
        start_hours_variation=1.23,
        expected_daily_hours=8.8,
        max_daily_hours=10,
        target_month=month,
        target_year=2026,
        rng=Random(month),
    )
    punches = simulator.generate()
    durations = [end - start for start, end in zip(punches[::2], punches[1::2], strict=True)]
    assert sum(durations, timedelta()) == timedelta(minutes=588 * len(durations))
    assert all(timedelta(hours=1) < duration <= timedelta(hours=11) for duration in durations)
    assert all(left < right for left, right in pairwise(punches))


def test_impossible_target_and_explicit_best_effort() -> None:
    simulator = PunchSimulator(expected_daily_hours=8.8, max_daily_hours=10)
    with pytest.raises(ScheduleNotPossible, match="unreachable"):
        simulator.generate()
    simulator.enable_best_effort = True
    assert len(simulator.generate()) == 2 * len(simulator.get_business_days())
    assert simulator.generate_punches(0, []) == []


def test_invalid_ranges_fail_before_generating() -> None:
    with pytest.raises(ValueError, match="Minute range"):
        PunchSimulator(start_min=59, stop_min=59)
    with pytest.raises(ValueError, match="Daily hours"):
        PunchSimulator(expected_daily_hours=9, max_daily_hours=8)
    with pytest.raises(ValueError, match="same day"):
        PunchSimulator(start_hours=22)


def test_coordinate_variation_is_bounded_and_nonconstant() -> None:
    gps = GpsOscilator(-23.5, -46.6, rng=Random(42))
    points = [gps.generate_latlong() for _ in range(100)]
    assert len(set(points)) == 100
    assert all(abs(lat + 23.5) <= 0.00002 and abs(lon + 46.6) <= 0.00002 for lat, lon in points)
