from datetime import date, timedelta

import pytest

from pontomaisoumenos.holidays import OptionalHoliday, business_days


@pytest.mark.parametrize(
    "monday",
    [date(2022, 2, 28), date(2024, 2, 12), date(2025, 3, 3), date(2026, 2, 16), date(2027, 2, 8), date(2028, 2, 28)],
)
def test_carnival_is_calculated_each_year_across_month_boundaries(monday: date) -> None:
    for day in (monday, monday + timedelta(days=1)):
        assert day not in business_days(day.year, day.month)
        assert day in business_days(day.year, day.month, enabled_optional_holidays=())
    wednesday = monday + timedelta(days=2)
    assert wednesday in business_days(wednesday.year, wednesday.month)


@pytest.mark.parametrize(
    ("holiday", "days_off"),
    [
        ("carnival", {date(2026, 2, 16), date(2026, 2, 17)}),
        ("ash_wednesday", {date(2026, 2, 18)}),
        ("corpus_christi", {date(2026, 6, 4)}),
        ("public_servants_day", {date(2026, 10, 28)}),
        ("christmas_eve", {date(2026, 12, 24)}),
        ("new_years_eve", {date(2026, 12, 31)}),
    ],
)
def test_enabling_an_optional_holiday_excludes_only_its_dates(
    holiday: OptionalHoliday, days_off: set[date], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGUAGE", "en_US")
    public_only = {day for month in range(1, 13) for day in business_days(2026, month, enabled_optional_holidays=())}
    enabled = {
        day for month in range(1, 13) for day in business_days(2026, month, enabled_optional_holidays=(holiday,))
    }
    assert public_only - enabled == days_off
    assert enabled <= public_only


def test_optional_policy_preserves_state_public_holidays() -> None:
    assert date(2026, 2, 16) in business_days(2026, 2, "RJ", enabled_optional_holidays=())
    assert date(2026, 2, 17) not in business_days(2026, 2, "RJ", enabled_optional_holidays=())
    assert date(2026, 4, 23) not in business_days(2026, 4, "RJ", enabled_optional_holidays=())
    assert date(2026, 4, 23) in business_days(2026, 4, "SP", enabled_optional_holidays=())
