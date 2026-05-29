"""Интеграционный тест: реальные SQLAlchemy-репозитории на in-memory SQLite.

Проверяем основное: upsert (ON CONFLICT) работает; маппинг entity↔model двусторонний.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.domain.entities.habit import Habit
from src.domain.entities.habit_log import HabitLog
from src.domain.entities.user import User
from src.domain.value_objects.category import Category
from src.infrastructure.database.repositories.habit_repo import (
    SqlAlchemyHabitLogRepository,
    SqlAlchemyHabitRepository,
)
from src.infrastructure.database.repositories.user_repo import SqlAlchemyUserRepository


@pytest.mark.asyncio
async def test_create_habit_persists_with_id(db):
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    await users.save(User(id=1, username="u", first_name="A"))

    h = Habit(id=None, user_id=1, name="Бег", category=Category.SPORT)
    saved = await habits.add(h)
    assert saved.id is not None
    fetched = await habits.get(saved.id)
    assert fetched is not None
    assert fetched.name == "Бег"
    assert fetched.category == Category.SPORT


@pytest.mark.asyncio
async def test_log_upsert_updates_existing(db):
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)

    await users.save(User(id=1, username="u", first_name="A"))
    saved = await habits.add(Habit(id=None, user_id=1, name="Бег"))

    today = date(2026, 5, 23)
    await logs.upsert(HabitLog(habit_id=saved.id, user_id=1, log_date=today, completed=True))
    await logs.upsert(HabitLog(habit_id=saved.id, user_id=1, log_date=today, completed=False))

    completed_dates = await logs.list_completed_dates(saved.id)
    # После апдейта completed=False — лог не считается выполненным.
    assert today not in completed_dates


@pytest.mark.asyncio
async def test_today_status_returns_active_habits_with_completion_flag(db):
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)

    await users.save(User(id=1, username="u", first_name="A"))
    h1 = await habits.add(Habit(id=None, user_id=1, name="Бег"))
    h2 = await habits.add(Habit(id=None, user_id=1, name="Чтение"))
    # h3 деактивирована — не должна попасть в today_status
    h3 = await habits.add(Habit(id=None, user_id=1, name="Старая"))
    await habits.deactivate(h3.id, user_id=1)

    today = date(2026, 5, 23)
    await logs.upsert(HabitLog(habit_id=h1.id, user_id=1, log_date=today, completed=True))

    status = await logs.today_status(user_id=1, today=today)
    names = {h.name: completed for h, completed in status}
    assert names == {"Бег": True, "Чтение": False}
