"""MoodCorrelationUseCase: проверяем формулу средних и delta."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import pytest

from src.application.use_cases.mood import MoodCorrelationUseCase
from src.domain.entities.habit import Habit
from src.domain.entities.habit_log import HabitLog
from src.domain.entities.mood_entry import MoodEntry


@dataclass
class FakeHabitRepo:
    items: list[Habit] = field(default_factory=list)

    async def add(self, h): self.items.append(h); return h
    async def get(self, hid):
        return next((h for h in self.items if h.id == hid), None)
    async def list_for_user(self, uid, active_only=True):
        return [h for h in self.items if h.user_id == uid]
    async def deactivate(self, hid, uid): pass


@dataclass
class FakeLogRepo:
    logs: list[HabitLog] = field(default_factory=list)

    async def upsert(self, log): self.logs.append(log)
    async def list_for_habit(self, hid, since):
        return [l for l in self.logs if l.habit_id == hid and l.log_date >= since]
    async def list_completed_dates(self, hid):
        return [l.log_date for l in self.logs if l.habit_id == hid and l.completed]
    async def today_status(self, uid, today): return []


@dataclass
class FakeMoodRepo:
    items: list[MoodEntry] = field(default_factory=list)

    async def add(self, e): self.items.append(e)
    async def list_for_user(self, uid, since):
        return [m for m in self.items if m.user_id == uid and m.entry_date >= since]


@pytest.mark.asyncio
async def test_correlation_detects_positive_effect():
    habits = FakeHabitRepo()
    logs = FakeLogRepo()
    moods = FakeMoodRepo()

    habit = Habit(id=1, user_id=10, name="Медитация")
    habits.items.append(habit)

    base = date(2026, 5, 1)
    # 5 дней с медитацией → настроение 4-5.
    # 5 дней без → настроение 2-3.
    for i in range(5):
        d = base + timedelta(days=i)
        logs.logs.append(HabitLog(habit_id=1, user_id=10, log_date=d, completed=True))
        moods.items.append(MoodEntry(user_id=10, entry_date=d, score=4 + (i % 2)))
    for i in range(5, 10):
        d = base + timedelta(days=i)
        logs.logs.append(HabitLog(habit_id=1, user_id=10, log_date=d, completed=False))
        moods.items.append(MoodEntry(user_id=10, entry_date=d, score=2 + (i % 2)))

    uc = MoodCorrelationUseCase(habits, logs, moods)
    insights = await uc.execute(user_id=10, days=365)
    assert len(insights) == 1
    ins = insights[0]
    assert ins.habit_name == "Медитация"
    assert ins.avg_mood_when_done > ins.avg_mood_when_skipped
    assert ins.delta > 1.0


@pytest.mark.asyncio
async def test_correlation_returns_empty_when_too_little_data():
    habits = FakeHabitRepo()
    logs = FakeLogRepo()
    moods = FakeMoodRepo()
    # Только 2 отметки настроения — мало для выводов.
    moods.items.append(MoodEntry(user_id=10, entry_date=date(2026, 5, 1), score=3))
    moods.items.append(MoodEntry(user_id=10, entry_date=date(2026, 5, 2), score=4))

    uc = MoodCorrelationUseCase(habits, logs, moods)
    insights = await uc.execute(user_id=10, days=30)
    assert insights == []
