from app import main
from app.holidays import BrazilianHolidayCalendar
from datetime import timedelta
from pandas import date_range
from pandas.tseries.offsets import CustomBusinessDay


def test_get_business_days() -> None:
    br_holidays = BrazilianHolidayCalendar()
    bdays = CustomBusinessDay(holidays=br_holidays.holidays())
    _business_days = list(main.get_business_days(month=10,
                                                 year=2017))
    _expected_business_days = list(date_range(start="10/01/2017",
                                              end="10/31/2017",
                                              freq=bdays))
    assert _business_days == _expected_business_days


def test_convert_timedelta_to_hours() -> None:
    just_a_timedelta = timedelta(hours=100)
    assert 100 == main.convert_timedelta_to_hours(just_a_timedelta)
