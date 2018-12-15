from .configurations import get_configurations, \
    get_database_connection, get_logger
from .database.models import User, Punch, RsaKey
from .database.models import create_tables, drop_tables
from .punches import PunchSimulator
from .tasks import count_words
from datetime import datetime, timedelta

from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import exists
from sqlalchemy import create_engine
from uuid import uuid4
from os import getenv

CONFIGURATIONS = get_configurations()
__DB_ENGINE = create_engine(get_database_connection())
_db_session = sessionmaker(__DB_ENGINE)()
logger = get_logger()


# create_tables()  # TODO: Design an inteligent migrations execution
#                    and move it inside run migration (create database)
def get_default_user():
    # It's a POC and shouldn't be moved this way to production
    stmt = exists().where(User.email == "matheus.cunha@loggi.com")
    if not _db_session.query(User.email).filter(stmt).scalar():

        __default_password = '/E|q&3?wv&j#7$zd9f#aXUuF">atT9Ea'
        __created_date = datetime.now()
        default_user = User(id=uuid4(),
                            email="matheus.cunha@loggi.com",
                            password=__default_password,
                            active=True,
                            updated_at=__created_date,
                            created_at=__created_date)
        _db_session.add(default_user)
        _db_session.commit()
    return (_db_session.query(User)
                       .filter_by(email='matheus.cunha@loggi.com')
                       .first())


# Sending just one bulk because it will never be greater than 70 values
# assuming that month_days * 2 (daily punches, in and out)
# where 0 < month_days <= 31
def save_punches(from_simulator: PunchSimulator,
                 user: User) -> None:
    _punches = []
    for punch_at in from_simulator.generate():
        _current_time = datetime.now()
        _punches.append(Punch(
            id=str(uuid4()),
            user_id=str(user.id),
            should_punch_at=punch_at,
            done=False,
            updated_at=_current_time,
            created_at=_current_time))
    _db_session.add_all(_punches)
    _db_session.commit()


def main() -> None:
    __CURRENT_DATE = datetime.now()
    # Possible timerange to control the "work journey"
    punch_it = PunchSimulator(
        possible_minutes_start=CONFIGURATIONS.getint(
            "working_hours",
            "possible_minutes_variation_start"),
        possible_minutes_stop=CONFIGURATIONS.getint(
            "working_hours",
            "possible_minutes_variation_end"),
        possible_start_hours=CONFIGURATIONS.getint("working_hours",
                                                   "possible_start_hour"),
        possible_start_hours_variation=CONFIGURATIONS.getfloat(
            "working_hours",
            "accepted_start_hour_variation"),
        expected_daily_hours=CONFIGURATIONS.getfloat("working_hours",
                                                     "expected_daily_hours"),
        max_daily_hours=CONFIGURATIONS.getint("working_hours",
                                              "maximum_daily_working_hours"),
        lunch_time=CONFIGURATIONS.getint("working_hours", "lunch_time"),
        target_month=int(getenv("TARGET_MONTH") or __CURRENT_DATE.month),
        target_year=int(getenv("TARGET_YEAR") or __CURRENT_DATE.year)
    )
    # Reads the default user and its RSA key from database
    _default_user = get_default_user()
    user_rsa_key = _db_session.query(RsaKey) \
                              .filter_by(user_id=str(_default_user.id)) \
                              .first()

    # Save punches for this user on database
    save_punches(from_simulator=punch_it,
                 user=_default_user)
    __values = _db_session.query(Punch) \
                          .filter_by(user_id=str(_default_user.id)) \
                          .all()

    for _result in __values:
        if _result.should_punch_at < __CURRENT_DATE:
            continue
        _key = "schedule-punch-for-{user}-at-{date}".format(
            user=_default_user.id,
            date=_result.should_punch_at.strftime("%d-%m-%y-%H:%M"))
        punch_at = _result.should_punch_at - datetime.now()
        logger.info("Registering value for punch %s in %s" %
                (_key, round(punch_at.total_seconds() * 1000)))
        count_words.send_with_options(
            args=(_default_user.email, _default_user.password,),
            delay=round(punch_at.total_seconds() * 1000))


if __name__ == "__main__":
    if getenv("RUN_MIGRATIONS", "no") == "yes":
        drop_tables()
        create_tables()

    main()
