#!/usr/bin/python3
# -*- coding: utf-8 -*-
from sqlalchemy import Column, String, MetaData, \
    UnicodeText, Text, DateTime, ForeignKey, \
    create_engine
from sqlalchemy.dialects.postgresql import BOOLEAN, UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
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
        tbl.drop(db)


class User(Base):
    __tablename__ = "USERS"
    id = Column(UUID, primary_key=True)
    email = Column(String(128), unique=True)
    password = Column(UnicodeText())
    active = Column(BOOLEAN)
    updated_at = Column(DateTime)
    created_at = Column(DateTime)


class Punches(Base):
    __tablename__ = "WORKING_PUNCHES"
    id = Column(UUID, primary_key=True)
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


class RsaKeys(Base):
    __tablename__ = "__RSA"
    id = Column(Text(), primary_key=True)
    private_key = Column(Text(), unique=True)
    user_id = Column(
        UUID,
        ForeignKey('USERS.id', ondelete='CASCADE'),
        nullable=False,
    )
    user = relationship('User', backref='rsa_keys')
