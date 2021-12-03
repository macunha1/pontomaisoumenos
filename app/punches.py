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
                 enable_best_effort: bool = False,
                 lunch_time: int = 1,
                 target_month: int = 1,
                 target_year: int = 1970):

        self.max_num_of_generations = max_num_of_generations
        self.enable_best_effort = enable_best_effort

        self.start_hours_variation = start_hours_variation

        if start_hours_variation == 1:
            self.start_min = 0
            self.stop_min = 0  # disable variation, since there will be none

            self.possible_minutes = numpy.array([0])
        else:
            self.start_min = start_min
            self.stop_min = stop_min

            self.possible_minutes = numpy.arange(start=self.start_min,
                                                 stop=self.stop_min)

        self.expected_daily_hours = expected_daily_hours
        self.max_daily_hours = max_daily_hours
        self.lunch_time = lunch_time

        self.target_month = target_month
        self.target_year = target_year

        self.start_hours = self \
            .calculate_possible_times(from_value=start_hours,
                                      variation=self.start_hours_variation)

        # Calculte the "mais ou menos" (values variation)
        self.variation_hours = (self.max_daily_hours /
                                self.expected_daily_hours)

        # Estimate the clock-out by start + expected hours + lunch time
        stop_hours = start_hours + self.expected_daily_hours \
            + self.lunch_time

        self.stop_hours = self \
            .calculate_possible_times(from_value=stop_hours,
                                      variation=self.variation_hours)

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
        hour = numpy.random.choice(possible_hours)
        minute = numpy.random.choice(self.possible_minutes)

        return datetime(year=from_datetime.year,
                        month=from_datetime.month,
                        day=from_datetime.day,
                        hour=hour,
                        minute=minute)

    def calculate_possible_times(self,
                                 from_value: int,
                                 variation: float) -> numpy.arange:
        start_values_at = int(from_value)
        stop_values_at = int(from_value * variation)

        if start_values_at == stop_values_at:
            # Both values are the smae, no way to create a range, return a
            # static list with the only value available
            return numpy.array([start_values_at])

        return numpy.arange(start=min(start_values_at, stop_values_at),
                            stop=max(start_values_at, stop_values_at))

    def generate_punches(self,
                         monthexpected_hours: int,
                         available_business_days: DatetimeIndex) -> list:
        expected_hours_td = timedelta(seconds=0)
        total_hours_td = timedelta(hours=monthexpected_hours)
        max_num_of_gens = self.max_num_of_generations

        # Use best shot as the buffer for the closest possible value
        best_shot = timedelta(seconds=0)
        best_generated_punches = []

        # Start to build value ranges until match the expected target
        while ((self.convert_timedelta_to_hours(expected_hours_td) !=
                self.convert_timedelta_to_hours(total_hours_td)) and
               max_num_of_gens > 0):

            expected_hours_td = timedelta(seconds=0)
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
                expected_hours_td += (random_end_time - random_start_time)

            # Get the closest value (smallest distance) to the total hours
            best_shot = min([best_shot, expected_hours_td],
                            key=lambda x: abs(total_hours_td-x))

            # Are the current generated punches the best shot we have so far?
            if best_shot == expected_hours_td:
                # Store it for later
                best_generated_punches = punch_results

        if max_num_of_gens == 0:
            if not self.enable_best_effort:
                raise Exception("Reached the limit of retries without success."
                                "Try to tune your configurations")

            punch_results = best_generated_punches

        return punch_results

    def generate(self) -> list:
        business_days = self.get_business_days()
        punches = self \
            .generate_punches(monthexpected_hours=((self.expected_daily_hours +
                                                    self.lunch_time) *
                                                   len(business_days)),
                              available_business_days=business_days)
        return punches
