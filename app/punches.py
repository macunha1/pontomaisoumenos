from calendar import monthrange
from datetime import datetime, timedelta
from pandas import date_range, DatetimeIndex
from pandas.tseries.offsets import CustomBusinessDay

from .holidays import BrazilianHolidayCalendar

import numpy


class PunchSimulator:
    # Generates "working hours" based on a given acceptable range.
    def __init__(self,
                 start_min: int = 0,
                 stop_min: int = 59,
                 start_hours: int = 10,
                 start_hours_variation: int = 1,
                 expected_daily_hours: int = 8,
                 max_daily_hours: int = 8,
                 max_num_of_generations: int = 12750,
                 lunch_time: int = 1,
                 target_month: int = 1,
                 target_year: int = 1970):

        self.start_min = start_min
        self.stop_min = stop_min
        self.start_hours = start_hours
        self.start_hours_variation = start_hours_variation

        self.expected_daily_hours = expected_daily_hours
        self.max_daily_hours = max_daily_hours
        self.max_num_of_generations = max_num_of_generations
        self.lunch_time = lunch_time

        self.target_month = target_month
        self.target_year = target_year

        # Calculte the "mais ou menos" (values variation)
        self.variation_hours = (self.max_daily_hours /
                                self.expected_daily_hours)
        self.stop_hours = self.start_hours + \
            self.expected_daily_hours + self.lunch_time

        self.start_hours = self \
            .calculate_possible_times(from_value=self.start_hours,
                                      variation=self.start_hours_variation)

        self.stop_hours = self \
            .calculate_possible_times(from_value=self.stop_hours,
                                      variation=self.variation_hours)

        self.possible_minutes = numpy.arange(start=self.start_min,
                                             stop=self.stop_min)

    def get_business_days(self) -> DatetimeIndex:
        brazilian_calendar = BrazilianHolidayCalendar()

        custom_business_day = \
            CustomBusinessDay(holidays=brazilian_calendar.holidays())

        month_length = monthrange(self.target_year,
                                  self.target_month)[1]

        start_at = datetime(self.target_year, self.target_month, 1)
        finish_at = datetime(self.target_year, self.target_month, month_length)

        return date_range(start=start_at.strftime("%m/%d/%y"),
                          end=finish_at.strftime("%m/%d/%y"),
                          freq=custom_business_day)

    def convert_timedelta_to_hours(self, from_time: timedelta) -> int:
        return from_time.total_seconds()//3600

    def get_possible_datetime(self,
                              possible_hours: numpy.arange,
                              from_datetime: datetime) -> datetime:
        return datetime(year=from_datetime.year,
                        month=from_datetime.month,
                        day=from_datetime.day,
                        hour=numpy.random.choice(possible_hours),
                        minute=numpy.random.choice(self.possible_minutes))

    def calculate_possible_times(self,
                                 from_value: int,
                                 variation: float) -> numpy.arange:
        start_values_at = int(from_value)
        stop_values_at = int(from_value * variation)
        return numpy.arange(start=min(start_values_at, stop_values_at),
                            stop=max(start_values_at, stop_values_at))

    def generate_punches(self,
                         monthexpected_hours: int,
                         available_business_days: DatetimeIndex) -> list:
        expected_hours_td = timedelta(hours=monthexpected_hours - 2)
        total_hours_td = timedelta(hours=monthexpected_hours)
        max_num_of_gens = self.max_num_of_generations

        # Start to build value ranges until match the expected target
        while ((self.convert_timedelta_to_hours(expected_hours_td) !=
                self.convert_timedelta_to_hours(total_hours_td)) and
               max_num_of_gens > 0):

            expected_hours_td = timedelta()
            max_num_of_gens -= 1
            punch_results = []

            for business_day in available_business_days:
                # Generates the start of the "working journey"
                random_start_time = self \
                    .get_possible_datetime(possible_hours=self.start_hours,
                                           from_datetime=business_day)
                punch_results.append(random_start_time)

                # Generates the end of the "working journey"
                random_end_time = self \
                    .get_possible_datetime(possible_hours=self.stop_hours,
                                           from_datetime=business_day)
                punch_results.append(random_end_time)

                # Total hours "worked" during the given "business_day"
                expected_hours_td += random_end_time - random_start_time

        if max_num_of_gens == 0:
            raise Exception("Reached the limit of retries without success."
                            "Try to tune your configurations")
        return punch_results

    def generate(self) -> list:
        business_days = self.get_business_days()
        punches = self \
            .generate_punches(monthexpected_hours=((self.expected_daily_hours +
                                                    self.lunch_time) *
                                                   len(business_days)),
                              available_business_days=business_days)
        return punches
