from datetime import datetime, timedelta
from calendar import monthrange
from configparser import ConfigParser
from pandas import date_range, DatetimeIndex
from pandas.tseries.offsets import CustomBusinessDay
from holidays import BrazilianHolidayCalendar
from os import getenv, path
import numpy


def get_business_days(month: int, year: int) -> DatetimeIndex:
    _current_month_length = monthrange(year, month)[1]

    _start_at_date = datetime(year, month, 1)
    _end_at_date = datetime(year, month, _current_month_length)

    brazilian_calendar = BrazilianHolidayCalendar()
    custom_business_day = CustomBusinessDay(
        holidays=brazilian_calendar.holidays())

    return date_range(start=_start_at_date.strftime("%m/%d/%y"),
                      end=_end_at_date.strftime("%m/%d/%y"),
                      freq=custom_business_day)


def format_human_readable(from_date: datetime) -> str:
    return from_date.strftime("%d-%m-%y %H:%M")


def convert_timedelta_to_hours(from_time: timedelta) -> int:
    return from_time.total_seconds()//3600


def get_possible_datetime(from_datetime: datetime,
                          possible_hour: numpy.ndarray,
                          possible_minute: numpy.ndarray) -> datetime:
    return datetime(year=from_datetime.year,
                    month=from_datetime.month,
                    day=from_datetime.day,
                    hour=numpy.random.choice(possible_hour),
                    minute=numpy.random.choice(possible_minute))


def calculate_possible_times(from_value: int,
                             variation: float) -> numpy.arange:
    _start_at_value = int(from_value)
    _stop_at_value = int(from_value * variation)
    return numpy.arange(start=min(_start_at_value, _stop_at_value),
                        stop=max(_start_at_value, _stop_at_value))


def generate_punches(month_expected_hours: int,
                     available_business_days: DatetimeIndex) -> list:
    _expected_hours_td = timedelta(hours=month_expected_hours - 2)
    _total_hours_td = timedelta(hours=month_expected_hours)
    # Start to build value ranges until match the expected target
    while (convert_timedelta_to_hours(_expected_hours_td) !=
            convert_timedelta_to_hours(_total_hours_td)):
        _expected_hours_td = timedelta()
        punch_results = []
        for __day in available_business_days:
            __random_start_time = get_possible_datetime(
                from_datetime=__day,
                possible_hour=POSSIBLE_START_HOURS,
                possible_minute=POSSIBLE_MINUTES)

            punch_results.append(
                format_human_readable(__random_start_time))

            __random_end_time = get_possible_datetime(
                from_datetime=__day,
                possible_hour=POSSIBLE_STOP_HOURS,
                possible_minute=POSSIBLE_MINUTES)
            punch_results.append(
                format_human_readable(__random_end_time))
            _expected_hours_td += __random_end_time - __random_start_time
    return punch_results


def main(target_month: int, target_year: int) -> list:
    _business_days = get_business_days(month=target_month,
                                       year=target_year)
    return generate_punches(
        month_expected_hours=(EXPECTED_DAILY_HOURS +
                              LUNCH_TIME) * len(_business_days),
        available_business_days=_business_days)


if __name__ == "__main__":
    configuration = ConfigParser()
    APPLICATION_ROOT_PATH = path.abspath(
        path.join(path.dirname(__file__), ".."))

    configuration.read(
        path.join(APPLICATION_ROOT_PATH, "config", "default.toml"))
    # Possible timerange to control the "work journey"
    POSSIBLE_MINUTES = numpy.arange(
        start=configuration.getint("working_hours",
                                   "possible_minutes_variation_start"),
        stop=configuration.getint("working_hours",
                                  "possible_minutes_variation_end"))
    _possible_start_hour = configuration.getint("working_hours",
                                                "possible_start_hour")

    POSSIBLE_START_HOURS = calculate_possible_times(
        from_value=_possible_start_hour,
        variation=configuration.getfloat("working_hours",
                                         "accepted_start_hour_variation"))

    EXPECTED_DAILY_HOURS = configuration.getfloat("working_hours",
                                                  "expected_daily_hours")
    MAX_DAILY_HOURS = configuration.getint("working_hours",
                                           "maximum_daily_working_hours")

    LUNCH_TIME = configuration.getint("working_hours", "lunch_time")
    POSSIBLE_STOP_HOURS = calculate_possible_times(
        from_value=_possible_start_hour + EXPECTED_DAILY_HOURS + LUNCH_TIME,
        variation=MAX_DAILY_HOURS/EXPECTED_DAILY_HOURS)

    __CURRENT_DATE = datetime.now()
    TARGET_MONTH = int(getenv("TARGET_MONTH") or __CURRENT_DATE.month)
    TARGET_YEAR = int(getenv("TARGET_YEAR") or __CURRENT_DATE.year)
    _results = main(target_month=TARGET_MONTH, target_year=TARGET_YEAR)

    print("Perfect punches")
    print("\n".join(_results))
