"""ORM-модели SQLAlchemy.

Принципиально отделены от domain-entities: тип ORM-моделей утечь в domain не должен,
маппинг делается в репозиториях явными `_to_entity` / `_to_model` функциями.
Это даёт независимость domain от выбора ORM.
"""
from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str] = mapped_column(String(64), default="")
    first_name: Mapped[str] = mapped_column(String(128), default="")
    points: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    reminder_time: Mapped[time] = mapped_column(Time, default=time(9, 0))
    coaching_mode: Mapped[str] = mapped_column(String(16), default="template")
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Персонализация (онбординг). См. domain.value_objects.motivation_style.
    motivation_style: Mapped[str] = mapped_column(String(32), default="not_set")
    priority_focus: Mapped[str] = mapped_column(String(32), default="not_set")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Long-term memory (LLM-сгенерированная сводка о пользователе).
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    memory_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Recovery mode (#3).
    recovery_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    recovery_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_insight_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class HabitModel(Base):
    __tablename__ = "habits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(32), default="Общее")
    frequency: Mapped[str] = mapped_column(String(64), default="daily")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Количественные привычки и цели.
    target_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_goal: Mapped[bool] = mapped_column(Boolean, default=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)


class HabitLogModel(Base):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("habit_id", "log_date", name="uq_habit_log_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    habit_id: Mapped[int] = mapped_column(Integer, ForeignKey("habits.id"), index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    log_date: Mapped[date] = mapped_column(Date, index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)
    value: Mapped[float] = mapped_column(Float, default=1.0)
    logged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AchievementModel(Base):
    __tablename__ = "achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    code: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    earned_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class MoodEntryModel(Base):
    __tablename__ = "mood_entries"
    __table_args__ = (UniqueConstraint("user_id", "entry_date", name="uq_user_mood_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CoachMessageModel(Base):
    __tablename__ = "coach_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
