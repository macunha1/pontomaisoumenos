from datetime import datetime, timedelta
from calendar import monthrange
from pandas import date_range, DatetimeIndex
from pandas.tseries.offsets import CustomBusinessDay
from .holidays import BrazilianHolidayCalendar
import numpy


class PunchSimulator:
    def __init__(self,
                 possible_minutes_start: int,
                 possible_minutes_stop: int,
                 possible_start_hours: int,
                 possible_start_hours_variation: int,
                 expected_daily_hours: int,
                 max_daily_hours: int,
                 lunch_time: int,
                 target_month: int,
                 target_year: int):
        self.possible_minutes_start = possible_minutes_start
        self.possible_minutes_stop = possible_minutes_stop
        self.possible_start_hours = possible_start_hours
        self.possible_start_hours_variation = possible_start_hours_variation

        self.expected_daily_hours = expected_daily_hours
        self.max_daily_hours = max_daily_hours
        self.possible_hours_variation = (self.max_daily_hours /
                                         self.expected_daily_hours)
        self.lunch_time = lunch_time
        self.possible_stop_hours = self.possible_start_hours + \
            self.expected_daily_hours + self.lunch_time
        self.target_month = target_month
        self.target_year = target_year

        self.possible_start_hours = self.calculate_possible_times(
            from_value=self.possible_start_hours,
            variation=self.possible_start_hours_variation)

        self.possible_stop_hours = self.calculate_possible_times(
            from_value=self.possible_stop_hours,
            variation=self.possible_hours_variation)

        self.possible_minutes = numpy.arange(start=self.possible_minutes_start,
                                             stop=self.possible_minutes_stop)

    def get_business_days(self) -> DatetimeIndex:
        _current_month_length = monthrange(self.target_year,
                                           self.target_month)[1]

        _start_at_date = datetime(self.target_year, self.target_month, 1)
        _end_at_date = datetime(self.target_year,
                                self.target_month,
                                _current_month_length)

        brazilian_calendar = BrazilianHolidayCalendar()
        custom_business_day = CustomBusinessDay(
            holidays=brazilian_calendar.holidays())

        return date_range(start=_start_at_date.strftime("%m/%d/%y"),
                          end=_end_at_date.strftime("%m/%d/%y"),
                          freq=custom_business_day)

    def convert_timedelta_to_hours(self, from_time: timedelta) -> int:
        return from_time.total_seconds()//3600

    def get_possible_datetime(self,
                              possible_hours: numpy.arange,
                              possible_minutes: numpy.arange,
                              from_datetime: datetime) -> datetime:
        return datetime(year=from_datetime.year,
                        month=from_datetime.month,
                        day=from_datetime.day,
                        hour=numpy.random.choice(possible_hours),
                        minute=numpy.random.choice(possible_minutes))

    def calculate_possible_times(self,
                                 from_value: int,
                                 variation: float) -> numpy.arange:
        _start_at_value = int(from_value)
        _stop_at_value = int(from_value * variation)
        return numpy.arange(start=min(_start_at_value, _stop_at_value),
                            stop=max(_start_at_value, _stop_at_value))

    def generate_punches(self,
                         month_expected_hours: int,
                         available_business_days: DatetimeIndex) -> list:
        _expected_hours_td = timedelta(hours=month_expected_hours - 2)
        _total_hours_td = timedelta(hours=month_expected_hours)
        # Start to build value ranges until match the expected target
        while (self.convert_timedelta_to_hours(_expected_hours_td) !=
                self.convert_timedelta_to_hours(_total_hours_td)):
            _expected_hours_td = timedelta()
            punch_results = []
            for __day in available_business_days:
                __random_start_time = self.get_possible_datetime(
                    possible_hours=self.possible_start_hours,
                    possible_minutes=self.possible_minutes,
                    from_datetime=__day)

                punch_results.append(__random_start_time)

                __random_end_time = self.get_possible_datetime(
                    possible_hours=self.possible_stop_hours,
                    possible_minutes=self.possible_minutes,
                    from_datetime=__day)
                punch_results.append(__random_end_time)
                _expected_hours_td += __random_end_time - __random_start_time
        return punch_results

    def generate(self) -> list:
        _business_days = self.get_business_days()
        return self.generate_punches(
            month_expected_hours=(self.expected_daily_hours +
                                  self.lunch_time) * len(_business_days),
            available_business_days=_business_days)
