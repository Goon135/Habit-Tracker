"""Запись о выполнении привычки за конкретный день."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class HabitLog:
    habit_id: int
    user_id: int
    log_date: date
    completed: bool
    value: float = 1.0  # Количественные привычки (страницы, минуты).
    logged_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
