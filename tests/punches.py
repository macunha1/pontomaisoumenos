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


def test_static_working_journey_generation() -> None:
    daily_working_journey = 8  # hours

    punch_simulator = PunchSimulator(lunch_time=0,
                                     expected_daily_hours=daily_working_journey,
                                     target_month=11,
                                     target_year=2017)

    bdays = CustomBusinessDay(holidays=br_holidays.holidays())
    monthly_working_journey = len(bdays) * daily_working_journey

    generated_punches = punch_simulator.generate()

    total_punched_timedelta = 0

    for index in range(0, len(generated_punches), 2):
        clockin_punch = generated_punches[index]
        clickout_punch = generated_punches[index+1]
        total_punched_timedelta += (clickout_punch - clockin_punch)

    total_generated_hours = punch_simulator \
        .convert_timedelta_to_hours(total_punched_timedelta)

    assert total_generated_hours == monthly_working_journey
