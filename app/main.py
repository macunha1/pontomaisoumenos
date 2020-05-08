from datetime import datetime
from os import getenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import exists
from sqlalchemy import create_engine
from uuid import uuid4

from .configurations import get_configurations, \
    get_database_connection, get_logger
from .database.models import User, Punch
from .database.models import create_tables, drop_tables
from .gps import GpsOscilator
from .punches import PunchSimulator
from .tasks import register_punch

CONFIGURATIONS = get_configurations()
__DB_ENGINE = create_engine(get_database_connection())
database_session = sessionmaker(__DB_ENGINE)()
logger = get_logger()


def get_default_user(user_email: str):
    stmt = exists().where(User.email == user_email)
    if not database_session.query(User.email).filter(stmt).scalar():

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
def save_punches(from_simulator: PunchSimulator,
                 user: User) -> None:
    punches = []
    for punch_at in from_simulator.generate():
        current_time = datetime.now()
        punches.append(Punch(
            id=str(uuid4()),
            user_id=str(user.id),
            should_punch_at=punch_at,
            done=False,
            updated_at=current_time,
            created_at=current_time))
    database_session.add_all(punches)
    database_session.commit()
    return punches


def generate_monthly_working_hours() -> None:
    CURRENT_DATE = datetime.now()
    # Possible timerange to control the "work journey"
    punch_it = PunchSimulator(possible_minutes_start=CONFIGURATIONS
                              .getint("working_hours",
                                      "possible_minutes_variation_start"),
                              possible_minutes_stop=CONFIGURATIONS
                              .getint("working_hours",
                                      "possible_minutes_variation_end"),
                              possible_start_hours=CONFIGURATIONS
                              .getint("working_hours",
                                      "possible_start_hour"),
                              possible_start_hours_variation=CONFIGURATIONS
                              .getfloat(
                                  "working_hours",
                                  "accepted_start_hour_variation"),
                              expected_daily_hours=CONFIGURATIONS
                              .getfloat("working_hours",
                                        "expected_daily_hours"),
                              max_daily_hours=CONFIGURATIONS
                              .getint("working_hours",
                                      "maximum_daily_working_hours"),
                              lunch_time=CONFIGURATIONS
                              .getint("working_hours",
                                      "lunch_time"),
                              target_month=int(getenv("TARGET_MONTH") or
                                               CURRENT_DATE.month),
                              target_year=int(getenv("TARGET_YEAR") or
                                              CURRENT_DATE.year))

    # Reads the current execution user from database
    current_user = get_default_user(CONFIGURATIONS.get("user", "email"),
                                    CONFIGURATIONS.get("user", "password"))

    # Generates a random geolocation based on the latitude and longitude configured
    gps = GpsOscilator(static_latitude=CONFIGURATIONS.getfloat("location",
                                                               "latitude"),
                       static_longitude=CONFIGURATIONS.getfloat("location",
                                                                "longitude"))
    static_latitude, static_longitude = gps.generate_latlong()
    user_work_address = CONFIGURATIONS.get("location", "address")

    # Save punches for this user on database
    return save_punches(from_simulator=punch_it,
                        user=current_user)


def schedule_punches() -> None:
    CURRENT_DATE = datetime.now()

    scheduled_punches = database_session \
        .query(Punch) \
        .filter_by(user_id=str(current_user.id)) \
        .all() or generate_monthly_working_hours()

    # Schedule only the pending punches (the ones with future dates)
    # Change the implementation from Dramatiq to APScheduler
    # Ref: https://apscheduler.readthedocs.io/en/3.0/
    for scheduled_punch in scheduled_punches:
        if scheduled_punch.should_punch_at < CURRENT_DATE:
            continue

        punch_at = scheduled_punch.should_punch_at - datetime.now()
        logger.info("%s scheduled to punch at %s" %
                    (current_user.id,
                     scheduled_punch.should_punch_at.isoformat()))

        register_punch.send_with_options(args=(current_user.email,
                                               current_user.password,
                                               user_work_address,
                                               static_latitude,
                                               static_longitude),
                                         delay=round(punch_at
                                                     .total_seconds() *
                                                     1000))


def main() -> None:
    generate_monthly_working_hours()
    schedule_punches()


if __name__ == "__main__":
    if getenv("RUN_MIGRATIONS", "no") == "yes":
        drop_tables()
        create_tables()

    main()
