"""Привычка.

Поддерживает три модальности:
- Обычная привычка (булевая): выполнил или нет.
- Количественная привычка (#2): target_value + unit, пользователь отмечает
  фактический объём, считается прогресс.
- Цель (#6): is_goal=True, end_date — после истечения автоматически
  деактивируется планировщиком.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from src.domain.value_objects.category import Category
from src.domain.value_objects.frequency import Frequency


@dataclass
class Habit:
    id: int | None  # None пока не сохранена в БД
    user_id: int
    name: str
    category: Category = Category.GENERAL
    frequency: Frequency = field(default_factory=Frequency.daily)
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Количественные привычки (#2). target_value=None => булевая.
    # Пример: «выпить 3 литра воды» -> target_value=3.0, unit="л".
    target_value: float | None = None
    unit: str | None = None

    # Цели (#6). is_goal=True + end_date — привычка с дедлайном.
    # После end_date scheduler установит is_active=False.
    is_goal: bool = False
    end_date: date | None = None

    def deactivate(self) -> None:
        self.is_active = False

    @property
    def is_quantitative(self) -> bool:
        return self.target_value is not None and self.target_value > 0

    def progress_ratio(self, current_value: float) -> float:
        """Доля выполнения [0..1]. Для булевой привычки — 0 или 1."""
        if not self.is_quantitative:
            return 1.0 if current_value >= 1 else 0.0
        return min(current_value / self.target_value, 1.0)

    def is_completed(self, current_value: float) -> bool:
        """Считается ли привычка выполненной при таком значении."""
        if not self.is_quantitative:
            return current_value >= 1
        return current_value >= self.target_value

    def is_expired(self, today: date) -> bool:
        """Цель просрочена (для авто-архивации в #6)."""
        return self.is_goal and self.end_date is not None and today > self.end_date
