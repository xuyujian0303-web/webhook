from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RuleGroup(Base):
    __tablename__ = "rule_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    match_mode: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class RuleCondition(Base):
    __tablename__ = "rule_conditions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_group_id: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)


class PushRecord(Base):
    __tablename__ = "push_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_no: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    store_name: Mapped[str] = mapped_column(String(64), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False)
    rule_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    window_start: Mapped[str] = mapped_column(String(32), nullable=False)
    window_end: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )


class GlobalSetting(Base):
    __tablename__ = "global_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    setting_json: Mapped[str] = mapped_column(Text, nullable=False)
