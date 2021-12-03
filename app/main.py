from datetime import datetime
from os import getenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import exists
from sqlalchemy import create_engine
from typing import List, Dict, Tuple, Any
from uuid import uuid4

from .configurations import (get_configurations,
                             get_database_connection,
                             get_logger)
from .database.models import User, Punch
from .database.models import create_tables  # , drop_tables
from .gps import GpsOscilator
from .punches import PunchSimulator
from .tasks import register_punch

CONF = get_configurations()
database_session = sessionmaker(create_engine(get_database_connection()))()
logger = get_logger()


def get_default_user(user_email: str) -> User:
    if not database_session.query(User.email) \
                           .filter(exists().where(User.email == user_email)) \
                           .scalar():
        created_date = datetime.now()
        default_user = User(id=uuid4(),
                            email=user_email,
                            active=True,
                            updated_at=created_date,
                            created_at=created_date)
        database_session.add(default_user)
        database_session.commit()
    return (database_session.query(User)
            .filter_by(email=user_email)
            .first())  # Ensures user creation


# Sending just one bulk because it will never be greater than 70 values
# assuming that month_days * 2 (daily punches, in and out)
# where 0 < month_days <= 31
def save_punches(simulator: PunchSimulator,
                 user: User) -> None:
    punches = []

    for punch_at in simulator.generate():
        current_time = datetime.now()
        punches.append(Punch(id=str(uuid4()),
                             user_id=str(user.id),
                             should_punch_at=punch_at,
                             done=False,
                             updated_at=current_time,
                             created_at=current_time))

    database_session.add_all(punches)
    database_session.commit()

    return punches


def parse_configurations() -> Dict[str, Any]:
    current_date = datetime.now()
    configparsed = {
        "start_min": CONF.getint("working_hours",
                                 "possible_minutes_variation_start"),
        "stop_min": CONF.getint("working_hours",
                                "possible_minutes_variation_end"),
        "start_hours": CONF.getint("working_hours",
                                   "possible_start_hour"),
        "max_num_of_generations": CONF.getint("algorithm", "max_num_of_gens"),
        "enable_best_effort": CONF.getboolean("algorithm",
                                              "enable_best_effort"),
        "start_hours_variation": CONF.getfloat("working_hours",
                                               "accepted_start_hour_variation"),
        "expected_daily_hours": CONF.getfloat("working_hours",
                                              "expected_daily_hours"),
        "max_daily_hours": CONF.getint("working_hours",
                                       "maximum_daily_working_hours"),
        "lunch_time": CONF.getint("working_hours",
                                  "lunch_time"),
        "target_month": int(getenv("TARGET_MONTH") or
                            current_date.month),
        "target_year": int(getenv("TARGET_YEAR") or
                           current_date.year)
    }
    return configparsed


def get_oscilated_latlong() -> Tuple[float, float]:
    # Generates a random geolocation based on latitude and longitude confs
    gps = GpsOscilator(static_latitude=CONF.getfloat("location",
                                                     "latitude"),
                       static_longitude=CONF.getfloat("location",
                                                      "longitude"))
    return gps.generate_latlong()


def generate_monthly_working_hours(user: User) -> List[Punch]:
    configuration = parse_configurations()
    punch_simulator = PunchSimulator(**configuration)
    # Save punches for this user on database
    return save_punches(simulator=punch_simulator, user=user)


def schedule_punches(user: User) -> None:
    current_date = datetime.now()

    scheduled_punches = database_session \
        .query(Punch) \
        .filter_by(user_id=str(user.id)) \
        .all() or generate_monthly_working_hours(user)

    user_work_address = CONF.get("location", "address")
    latitude, longitude = get_oscilated_latlong()

    # Schedule only the pending punches (the ones with future dates)
    # TODO: Change the implementation from Dramatiq to APScheduler
    # Ref: https://apscheduler.readthedocs.io/en/3.0/
    for scheduled_punch in scheduled_punches:
        if scheduled_punch.should_punch_at < current_date:
            continue

        punch_at = scheduled_punch.should_punch_at - datetime.now()
        logger.info("%s scheduled to punch at %s" %
                    (user.id,
                     scheduled_punch.should_punch_at.isoformat()))

        register_punch \
            .send_with_options(args=(user.email,
                                     CONF.get("user", "password"),
                                     user_work_address,
                                     latitude,
                                     longitude),
                               delay=round(punch_at
                                           .total_seconds() * 1000))


def main() -> None:
    # Reads the current execution user from database
    user = get_default_user(CONF.get("user", "email"))
    schedule_punches(user)


if __name__ == "__main__":
    # TODO: Implement the argparser to support CLI
    if getenv("RUN_MIGRATIONS", "no") == "yes":
        # drop_tables()
        create_tables()

    main()
