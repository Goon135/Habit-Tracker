"""Серия выполнений привычки (streak)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class Streak:
    """Длина серии и дата последнего выполнения.

    Считается чистой функцией: дать список дат выполнений → получить streak.
    Никакого обращения к БД, чтобы юнит-тестить без моков.
    """
    length: int
    last_completion: date | None

    @classmethod
    def calculate(cls, completed_dates: Iterable[date], today: date) -> "Streak":
        sorted_dates = sorted(set(completed_dates), reverse=True)
        if not sorted_dates:
            return cls(length=0, last_completion=None)

        # Серия валидна, если последнее выполнение — сегодня или вчера.
        # Если "вчера" — у пользователя ещё есть шанс выполнить сегодня и не потерять серию.
        last = sorted_dates[0]
        if last < today - timedelta(days=1):
            return cls(length=0, last_completion=last)

        length = 0
        expected = last
        for d in sorted_dates:
            if d == expected:
                length += 1
                expected -= timedelta(days=1)
            elif d < expected:
                break
        return cls(length=length, last_completion=last)
