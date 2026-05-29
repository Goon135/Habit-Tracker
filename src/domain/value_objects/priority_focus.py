"""Что для пользователя важнее: непрерывная серия или общий процент выполнения.

Второй опрос онбординга. Влияет на:
- Формулировки коуча (упор на streak vs % выполнения).
- Логику предиктивных подсказок (срыв серии vs падение completion rate).
"""
from __future__ import annotations

from enum import Enum


class PriorityFocus(str, Enum):
    NOT_SET = "not_set"
    STREAK = "streak"            # серия дней важнее
    COMPLETION = "completion"    # общий процент выполнения важнее

    @property
    def label(self) -> str:
        return {
            PriorityFocus.STREAK: "🔥 Серия дней",
            PriorityFocus.COMPLETION: "📊 Общий прогресс",
        }.get(self, "Не задан")
