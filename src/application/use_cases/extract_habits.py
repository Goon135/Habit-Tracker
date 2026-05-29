"""Use case: извлечь привычки из произвольного текста и создать их.

Этап 1: HabitExtractor (LLM с tool use) → список ExtractedHabitDTO.
Этап 2: маппим в Habit и сохраняем.

Возвращаем созданные сущности — presentation покажет их пользователю
с возможностью отменить.
"""
from __future__ import annotations

from datetime import date, timedelta

from src.application.interfaces.ai_services import HabitExtractor
from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.value_objects.category import Category
from src.domain.value_objects.frequency import Frequency


class ExtractHabitsFromTextUseCase:
    def __init__(self, habits: HabitRepository, extractor: HabitExtractor) -> None:
        self._habits = habits
        self._extractor = extractor

    async def execute(self, user_id: int, free_text: str) -> list[Habit]:
        extracted = await self._extractor.extract(free_text)
        created: list[Habit] = []
        today = date.today()
        for item in extracted:
            freq = self._build_frequency(item)
            # Цель: считаем end_date из duration_days. Если LLM пометил is_goal,
            # но duration_days не пришло — экстрактор уже подставил дефолт 30.
            end_date: date | None = None
            if item.is_goal and item.duration_days:
                end_date = today + timedelta(days=item.duration_days)
            habit = Habit(
                id=None,
                user_id=user_id,
                name=item.name,
                category=Category.from_string(item.category),
                frequency=freq,
                target_value=item.target_value,
                unit=item.unit,
                is_goal=item.is_goal and end_date is not None,
                end_date=end_date,
            )
            saved = await self._habits.add(habit)
            created.append(saved)
        return created

    @staticmethod
    def _build_frequency(item) -> Frequency:
        kind = (item.frequency_kind or "daily").lower()
        try:
            if kind == "weekly_n" and item.times_per_week:
                return Frequency.weekly(item.times_per_week)
            if kind == "weekdays" and item.weekdays:
                return Frequency.on_weekdays(set(item.weekdays))
        except ValueError:
            pass
        return Frequency.daily()
