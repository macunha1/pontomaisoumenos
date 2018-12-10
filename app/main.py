from datetime import datetime
from .configurations import get_configurations
from .database.models import create_tables
from .punches import calculate_possible_times, generate
from os import getenv
import numpy


def main():
    configuration = get_configurations()
    create_tables()
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
    return generate(target_month=TARGET_MONTH, target_year=TARGET_YEAR)


if __name__ == "__main__":
    _results = main()
    # TODO: Save in the DB all points
    # TODO: Retrieve all data from database
    # TODO: Use the retrieved data from database to schedule tasks with Celery

    print("Perfect punches")
    print("\n".join(_results))
