#!/usr/bin/python3
# -*- coding: utf-8 -*-
from sqlalchemy import Column, String, MetaData, \
    Text, Text, DateTime, ForeignKey, \
    create_engine
from sqlalchemy.dialects.postgresql import BOOLEAN, UUID
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
    id = Column(UUID(as_uuid=True),
                primary_key=True,
                default=uuid4)
    email = Column(String(128), unique=True)
    password = Column(Text)
    active = Column(BOOLEAN)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)


class Punch(Base):
    __tablename__ = "WORKING_PUNCHES"
    id = Column(UUID(as_uuid=True),
                primary_key=True,
                default=uuid4)
    user_id = Column(
        UUID,
        ForeignKey('USERS.id', ondelete='CASCADE'),
        nullable=False,
    )
    user = relationship('User', backref='punches')

    should_punch_at = Column(DateTime)
    done = Column(BOOLEAN)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)


class RsaKey(Base):
    __tablename__ = "__RSA"
    id = Column(UUID(as_uuid=True),
                primary_key=True,
                default=uuid4)
    private_key = Column(Text)
    user_id = Column(
        UUID,
        ForeignKey('USERS.id', ondelete='CASCADE'),
        nullable=False,
    )
    user = relationship('User', backref='rsa_keys')
