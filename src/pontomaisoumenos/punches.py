"""Bounded minute-resolution schedule generation without scientific runtime dependencies."""

from datetime import date, datetime, time, timedelta
from random import Random
from zoneinfo import ZoneInfo

from .holidays import DEFAULT_ENABLED_OPTIONAL_HOLIDAYS, OptionalHoliday, business_days


class ScheduleNotPossible(ValueError):
    pass


class PunchSimulator:
    def __init__(
        self,
        start_min: int = 0,
        stop_min: int = 59,
        start_hours: int = 10,
        start_hours_variation: float = 1,
        expected_daily_hours: float = 8,
        max_daily_hours: float = 8,
        enable_best_effort: bool = False,
        lunch_time: float = 1,
        target_month: int = 1,
        target_year: int = 1970,
        *,
        timezone: str = "America/Sao_Paulo",
        holiday_subdivision: str = "SP",
        enabled_optional_holidays: tuple[OptionalHoliday, ...] = DEFAULT_ENABLED_OPTIONAL_HOLIDAYS,
        rng: Random | None = None,
    ) -> None:
        if not 0 <= start_min < stop_min <= 60:
            raise ValueError("Minute range must be within [0, 60), with an exclusive upper bound")
        if not 0 < expected_daily_hours <= max_daily_hours < 24 or lunch_time < 0:
            raise ValueError("Daily hours must be positive and bounded by maximum daily hours")
        if max_daily_hours + lunch_time >= 24 or start_hours_variation <= 0:
            raise ValueError("Invalid generation bounds")
        date(target_year, target_month, 1)
        self.expected_daily_hours = expected_daily_hours
        self.lunch_time = lunch_time
        self.target_month = target_month
        self.target_year = target_year
        self.zone = ZoneInfo(timezone)
        self.holiday_subdivision = holiday_subdivision
        self.enabled_optional_holidays = enabled_optional_holidays
        self.rng = rng if rng is not None else Random()
        self.enable_best_effort = enable_best_effort
        minutes = range(start_min, stop_min) if start_hours_variation != 1 else range(1)
        start_range = self.calculate_possible_times(start_hours, start_hours_variation)
        end_hour = start_hours + expected_daily_hours + lunch_time
        end_range = self.calculate_possible_times(end_hour, max_daily_hours / expected_daily_hours)
        max_minutes = round((max_daily_hours + lunch_time) * 60)
        self.pairs: dict[int, list[tuple[int, int]]] = {}
        for hour in start_range:
            for minute in minutes:
                start = hour * 60 + minute
                for end in (end_hour * 60 + end_minute for end_hour in end_range for end_minute in minutes):
                    duration = end - start
                    if 0 <= start < end < 24 * 60 and lunch_time * 60 < duration <= max_minutes:
                        self.pairs.setdefault(duration, []).append((start, end))
        if not self.pairs:
            raise ScheduleNotPossible("Configured start/end ranges cannot produce a valid working day")

    @staticmethod
    def calculate_possible_times(from_value: float, variation: float) -> range:
        start, stop = sorted((int(from_value), int(from_value * variation)))
        if start < 0 or stop > 23:
            raise ValueError("Start/end hour ranges must stay within the same day")
        return range(start, max(start + 1, stop))

    @staticmethod
    def convert_timedelta_to_hours(from_time: timedelta) -> int:
        return int(from_time.total_seconds() // 3600)

    def get_business_days(self) -> list[date]:
        return business_days(
            self.target_year,
            self.target_month,
            self.holiday_subdivision,
            enabled_optional_holidays=self.enabled_optional_holidays,
        )

    def generate_punches(self, monthexpected_hours: float, available_business_days: list[date]) -> list[datetime]:
        if not 0 <= monthexpected_hours <= 24 * len(available_business_days):
            raise ValueError("Monthly target must fit within the available days")
        # Bit N means N total minutes are reachable. Each step adds one day's
        # duration. This replaces repeated whole-month random guessing.
        reachable = [1]
        durations = list(self.pairs)
        for _ in available_business_days:
            totals = 0
            for duration in durations:
                totals |= reachable[-1] << duration
            reachable.append(totals)
        target = round(monthexpected_hours * 60)
        if not (reachable[-1] >> target) & 1:
            if not self.enable_best_effort:
                raise ScheduleNotPossible("Monthly target is unreachable with the configured start/end ranges")
            lower = (reachable[-1] & ((1 << target) - 1)).bit_length() - 1
            upper_bits = reachable[-1] >> target
            upper = target + (upper_bits & -upper_bits).bit_length() - 1 if upper_bits else -1
            target = min((value for value in (lower, upper) if value >= 0), key=lambda value: abs(target - value))
        result: list[datetime] = []
        for index, day in reversed(list(enumerate(available_business_days))):
            possible = [value for value in durations if target >= value and (reachable[index] >> (target - value)) & 1]
            duration = self.rng.choice(possible)
            start, end = self.rng.choice(self.pairs[duration])
            midnight = datetime.combine(day, time(), tzinfo=self.zone)
            result.extend((midnight + timedelta(minutes=end), midnight + timedelta(minutes=start)))
            target -= duration
        result.reverse()
        return result

    def generate(self) -> list[datetime]:
        days = self.get_business_days()
        return self.generate_punches((self.expected_daily_hours + self.lunch_time) * len(days), days)
