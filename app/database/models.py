#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from sqlalchemy import (
    Boolean,
    Column,
    create_engine,
    DateTime,
    ForeignKey,
    MetaData,
    String,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from uuid import uuid4

from ..configurations import get_database_connection

Base = declarative_base()
db = create_engine(get_database_connection())
meta = MetaData(db)


def create_tables():
    _db_session = sessionmaker(db)()
    Base.metadata.create_all(db)
    _db_session.commit()


def drop_tables():
    for tbl in reversed(Base.metadata.sorted_tables):
        tbl.drop(db, checkfirst=True)


class User(Base):
    __tablename__ = "USERS"
    id = Column(String(36), primary_key=True, default=uuid4)
    email = Column(String(128), unique=True)
    active = Column(Boolean)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)


class Punch(Base):
    __tablename__ = "WORKING_PUNCHES"
    id = Column(String(36), primary_key=True, default=uuid4)

    user = relationship("User", backref="punches")
    user_id = Column(String,
                     ForeignKey("USERS.id", ondelete="CASCADE"),
                     nullable=False)

    should_punch_at = Column(DateTime)
    done = Column(Boolean)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)
