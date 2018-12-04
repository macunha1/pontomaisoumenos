from datetime import datetime, timedelta
from calendar import monthrange
from pandas import date_range
from pandas.tseries.offsets import CustomBusinessDay
from holidays import BrazilianHolidayCalendar
import numpy

# Application CONSTANTS
# Possible timerange to control the "work journey"
POSSIBLE_MINUTES = numpy.arange(0, 59)
POSSIBLE_START_HOURS = numpy.arange(9, 11)
POSSIBLE_STOP_HOURS = numpy.arange(18, 20)
EXPECTED_DAILY_HOUR = 8.8
# Current datetime values
__CURRENT_DATE = datetime.now()
CURRENT_MONTH_LENGTH = monthrange(__CURRENT_DATE.year,
                                  __CURRENT_DATE.month)[1]

_START_AT_DATE = datetime(__CURRENT_DATE.year,
                          __CURRENT_DATE.month,
                          1)
_STOP_AT_DATE = datetime(__CURRENT_DATE.year,
                         __CURRENT_DATE.month,
                         CURRENT_MONTH_LENGTH)

brazilian_calendar = BrazilianHolidayCalendar()
custom_business_day = CustomBusinessDay(holidays=brazilian_calendar.holidays())
_BUSINESS_DAYS = date_range(start=_START_AT_DATE.strftime("%m/%d/%y"),
                            end=_STOP_AT_DATE.strftime("%m/%d/%y"),
                            freq=custom_business_day)


def format_human_readable(from_date: datetime):
    return from_date.strftime("%d-%m-%y %H:%M")


def convert_timedelta_to_hours(from_time: timedelta):
    return from_time.total_seconds()//3600


month_expected_total = EXPECTED_DAILY_HOUR * len(_BUSINESS_DAYS)
_total_hours = timedelta(hours=month_expected_total)

expected_hours = timedelta(hours=month_expected_total - 2)
# Start to build value ranges until match the expected target
while (convert_timedelta_to_hours(expected_hours) !=
        convert_timedelta_to_hours(_total_hours)):
    expected_hours = timedelta()
    appointment_results = []
    for __day in _BUSINESS_DAYS:
        __random_start_time = datetime(
            __day.year, __day.month, __day.day,
            numpy.random.choice(POSSIBLE_START_HOURS),
            numpy.random.choice(POSSIBLE_MINUTES), 0)
        appointment_results.append(
            format_human_readable(__random_start_time))

        __random_end_time = datetime(
            __day.year, __day.month, __day.day,
            numpy.random.choice(POSSIBLE_STOP_HOURS),
            numpy.random.choice(POSSIBLE_MINUTES), 0)
        appointment_results.append(
            format_human_readable(__random_end_time))

        expected_hours += __random_end_time - __random_start_time

print("Perfect appointments")
print("\n".join(appointment_results))
