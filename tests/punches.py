from datetime import timedelta
from pandas import date_range
from pandas.tseries.offsets import CustomBusinessDay

from app.holidays import BrazilianHolidayCalendar
from app.punches import PunchSimulator


def test_get_business_days() -> None:
    br_holidays = BrazilianHolidayCalendar()
    punch_simulator = PunchSimulator(target_month=10, target_year=2017)

    bdays = CustomBusinessDay(holidays=br_holidays.holidays())
    simulator_bdays = punch_simulator.get_business_days()

    expected_business_days = date_range(start="10/01/2017",
                                        end="10/31/2017",
                                        freq=bdays)

    assert all(simulator_bdays == expected_business_days)


def test_convert_timedelta_to_hours() -> None:
    punch_simulator = PunchSimulator()
    simulated_hours = punch_simulator \
        .convert_timedelta_to_hours(timedelta(hours=100))

    assert 100 == simulated_hours
