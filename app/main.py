from datetime import datetime, timedelta
from calendar import monthrange
from pandas import date_range, DatetimeIndex
from pandas.tseries.offsets import CustomBusinessDay
from holidays import BrazilianHolidayCalendar
from os import getenv
import numpy

# Possible timerange to control the "work journey"
POSSIBLE_MINUTES = numpy.arange(0, 59)
POSSIBLE_START_HOURS = numpy.arange(9, 11)
POSSIBLE_STOP_HOURS = numpy.arange(18, 20)
EXPECTED_DAILY_HOUR = 8.8


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
        month_expected_hours=EXPECTED_DAILY_HOUR * len(_business_days),
        available_business_days=_business_days)


if __name__ == "__main__":
    __CURRENT_DATE = datetime.now()
    TARGET_MONTH = int(getenv("TARGET_MONTH", __CURRENT_DATE.month))
    TARGET_YEAR = int(getenv("TARGET_YEAR", __CURRENT_DATE.year))
    _results = main(target_month=TARGET_MONTH, target_year=TARGET_YEAR)

    print("Perfect punches")
    print("\n".join(_results))
