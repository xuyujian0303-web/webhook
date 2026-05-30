from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from wecom_sales_webhook_bot.rule_models import Base


def create_session_factory(database_url: str) -> sessionmaker:
    engine = create_engine(database_url, future=True)
    return sessionmaker(bind=engine, future=True)


def initialize_database(session_factory: sessionmaker) -> None:
    Base.metadata.create_all(session_factory.kw["bind"])
