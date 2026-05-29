"""Use case: редактировать существующую привычку (#5).

Принимает habit_id и опциональные поля для изменения. Если поле = None
(или специальное sentinel-значение для unit/end_date, где None — валид) —
оставляем как было. Так пользователь может менять только то, что нужно,
не пересоздавая привычку.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.value_objects.category import Category
from src.domain.value_objects.frequency import Frequency


# Sentinel: отличаем "не передано" от "явно установлено в None".
# Нужно для unit и end_date, где None — валидное значение.
class _Unset:
    pass


UNSET: _Unset = _Unset()


@dataclass
class UpdateHabitFields:
    """Какие поля нужно поменять. Поля типа _Unset означают «не трогать»."""
    name: str | _Unset = UNSET
    category: Category | _Unset = UNSET
    frequency: Frequency | _Unset = UNSET
    target_value: float | None | _Unset = UNSET
    unit: str | None | _Unset = UNSET
    is_goal: bool | _Unset = UNSET
    end_date: date | None | _Unset = UNSET


class UpdateHabitUseCase:
    def __init__(self, habits: HabitRepository) -> None:
        self._habits = habits

    async def execute(
        self,
        user_id: int,
        habit_id: int,
        fields: UpdateHabitFields,
    ) -> Habit | None:
        habit = await self._habits.get(habit_id)
        if habit is None or habit.user_id != user_id:
            return None

        if not isinstance(fields.name, _Unset):
            name = fields.name.strip()
            if not name:
                raise ValueError("habit name is empty")
            habit.name = name
        if not isinstance(fields.category, _Unset):
            habit.category = fields.category
        if not isinstance(fields.frequency, _Unset):
            habit.frequency = fields.frequency
        if not isinstance(fields.target_value, _Unset):
            if fields.target_value is not None and fields.target_value <= 0:
                raise ValueError("target_value must be positive")
            habit.target_value = fields.target_value
        if not isinstance(fields.unit, _Unset):
            habit.unit = fields.unit
        if not isinstance(fields.is_goal, _Unset):
            habit.is_goal = fields.is_goal
        if not isinstance(fields.end_date, _Unset):
            if fields.end_date is not None and fields.end_date < date.today():
                raise ValueError("end_date must be today or later")
            habit.end_date = fields.end_date

        # Если is_goal=True — end_date должен быть установлен.
        if habit.is_goal and habit.end_date is None:
            raise ValueError("goal habit must have end_date")

        return await self._habits.update(habit)
