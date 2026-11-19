from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from wecom_sales_webhook_bot.rule_models import Base


def create_session_factory(database_url: str) -> sessionmaker:
    if database_url.startswith("sqlite:///"):
        database_path = database_url.removeprefix("sqlite:///")
        if database_path not in {":memory:", ""}:
            Path(database_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, future=True)
    return sessionmaker(bind=engine, future=True)


def initialize_database(session_factory: sessionmaker) -> None:
    engine = session_factory.kw["bind"]
    Base.metadata.create_all(engine)
    # ``create_all`` does not alter existing SQLite databases.  Keep old local
    # installations usable when the flexible AND/OR condition group is added.
    columns = {item["name"] for item in inspect(engine).get_columns("rule_conditions")}
    if "condition_group" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE rule_conditions ADD COLUMN condition_group VARCHAR(16) NOT NULL DEFAULT 'all'"))
