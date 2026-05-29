"""CompleteHabitUseCase: интеграция domain-сервисов через application-оркестрацию.

Используем fake-репозитории (in-memory) вместо моков: код яснее, чем mock.assert_called_with,
и тест проверяет состояние, а не сигнатуры вызовов.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.domain.entities.achievement import Achievement
from src.domain.entities.habit import Habit
from src.domain.entities.habit_log import HabitLog
from src.domain.entities.user import User
from src.domain.value_objects.category import Category


@dataclass
class FakeUserRepo:
    users: dict[int, User] = field(default_factory=dict)

    async def get(self, user_id):
        return self.users.get(user_id)

    async def save(self, user):
        self.users[user.id] = user

    async def list_all_with_reminder(self):
        return list(self.users.values())


@dataclass
class FakeHabitRepo:
    habits: dict[int, Habit] = field(default_factory=dict)
    _next_id: int = 1

    async def add(self, habit):
        habit.id = self._next_id
        self._next_id += 1
        self.habits[habit.id] = habit
        return habit

    async def get(self, habit_id):
        return self.habits.get(habit_id)

    async def list_for_user(self, user_id, active_only=True):
        return [h for h in self.habits.values()
                if h.user_id == user_id and (not active_only or h.is_active)]

    async def deactivate(self, habit_id, user_id):
        h = self.habits.get(habit_id)
        if h and h.user_id == user_id:
            h.is_active = False


@dataclass
class FakeLogRepo:
    logs: list[HabitLog] = field(default_factory=list)

    async def upsert(self, log):
        # имитируем уникальность (habit_id, log_date)
        self.logs = [l for l in self.logs
                     if not (l.habit_id == log.habit_id and l.log_date == log.log_date)]
        self.logs.append(log)

    async def list_for_habit(self, habit_id, since):
        return [l for l in self.logs if l.habit_id == habit_id and l.log_date >= since]

    async def list_completed_dates(self, habit_id):
        return [l.log_date for l in self.logs if l.habit_id == habit_id and l.completed]

    async def today_status(self, user_id, today):
        return []  # тут не используется


@dataclass
class FakeAchievementRepo:
    granted: list[Achievement] = field(default_factory=list)

    async def grant(self, achievement):
        for a in self.granted:
            if a.user_id == achievement.user_id and a.code == achievement.code:
                return False
        self.granted.append(achievement)
        return True

    async def list_for_user(self, user_id):
        return [a for a in self.granted if a.user_id == user_id]

    async def list_codes_for_user(self, user_id):
        return {a.code for a in self.granted if a.user_id == user_id}


@pytest.fixture
def fakes():
    users = FakeUserRepo()
    habits = FakeHabitRepo()
    logs = FakeLogRepo()
    achs = FakeAchievementRepo()
    return users, habits, logs, achs


@pytest.mark.asyncio
async def test_completion_creates_log_grants_points_and_first_step_achievement(fakes):
    users, habits, logs, achs = fakes
    users.users[10] = User(id=10, username="u", first_name="U")
    await habits.add(Habit(id=None, user_id=10, name="Бег", category=Category.SPORT))

    uc = CompleteHabitUseCase(users, habits, logs, achs)
    today = date(2026, 5, 23)
    result = await uc.execute(user_id=10, habit_id=1, today=today)

    assert result.streak == 1
    assert result.points_earned == 10
    assert result.total_points == 10
    assert result.level == 1
    assert any("Первый шаг" in a["title"] for a in result.new_achievements)
    # Лог реально записан.
    assert len(logs.logs) == 1


@pytest.mark.asyncio
async def test_three_day_streak_unlocks_streak_3_achievement(fakes):
    users, habits, logs, achs = fakes
    users.users[10] = User(id=10, username="u", first_name="U")
    await habits.add(Habit(id=None, user_id=10, name="Бег"))

    uc = CompleteHabitUseCase(users, habits, logs, achs)
    base = date(2026, 5, 23)
    for offset in range(3):  # вчера-1, вчера, сегодня
        await uc.execute(user_id=10, habit_id=1, today=base - timedelta(days=2 - offset))

    codes = {a.code for a in achs.granted}
    assert "streak_3" in codes


@pytest.mark.asyncio
async def test_achievement_granted_only_once(fakes):
    """Если выполнить дважды на серии 3 — достижение всё равно одно."""
    users, habits, logs, achs = fakes
    users.users[10] = User(id=10, username="u", first_name="U")
    await habits.add(Habit(id=None, user_id=10, name="Бег"))

    uc = CompleteHabitUseCase(users, habits, logs, achs)
    base = date(2026, 5, 23)
    for offset in range(3):
        await uc.execute(user_id=10, habit_id=1, today=base - timedelta(days=2 - offset))
    # Повторное выполнение того же дня — upsert не создаёт новой записи.
    await uc.execute(user_id=10, habit_id=1, today=base)

    streak_3_count = sum(1 for a in achs.granted if a.code == "streak_3")
    assert streak_3_count == 1
