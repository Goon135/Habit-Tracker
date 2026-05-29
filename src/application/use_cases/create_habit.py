"""Use case: создать новую привычку или цель."""
from __future__ import annotations

from datetime import date

from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.value_objects.category import Category
from src.domain.value_objects.frequency import Frequency


class CreateHabitUseCase:
    def __init__(self, habits: HabitRepository) -> None:
        self._habits = habits

    async def execute(
        self,
        user_id: int,
        name: str,
        category: Category = Category.GENERAL,
        frequency: Frequency | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        is_goal: bool = False,
        end_date: date | None = None,
    ) -> Habit:
        name = name.strip()
        if not name:
            raise ValueError("habit name is empty")
        if target_value is not None and target_value <= 0:
            raise ValueError("target_value must be positive")
        if is_goal and end_date is None:
            raise ValueError("goal habit must have end_date")
        if is_goal and end_date is not None and end_date < date.today():
            raise ValueError("goal end_date must be in the future")
        habit = Habit(
            id=None,
            user_id=user_id,
            name=name,
            category=category,
            frequency=frequency or Frequency.daily(),
            target_value=target_value,
            unit=unit,
            is_goal=is_goal,
            end_date=end_date,
        )
        return await self._habits.add(habit)
