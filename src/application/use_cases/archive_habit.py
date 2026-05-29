"""Use case: архивировать привычку пользователя по идентификатору или названию.

Используется в двух местах:
- из UI (кнопка "удалить" в списке привычек) — по habit_id;
- из LLM-коуча через function calling — по человеко-читаемому названию,
  потому что в инструменте удобнее передавать строку, а не БД-идентификатор.

Реально не удаляем строку из БД, а ставим is_active=False. Это сохраняет
исторические логи для аналитики и позволяет восстановить привычку.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ArchiveResult:
    archived_habit_id: int
    archived_habit_name: str


class ArchiveHabitUseCase:
    def __init__(self, habits: HabitRepository) -> None:
        self._habits = habits

    async def by_id(self, user_id: int, habit_id: int) -> ArchiveResult | None:
        """Архивация по точному ID — для UI."""
        habit = await self._habits.get(habit_id)
        if habit is None or habit.user_id != user_id or not habit.is_active:
            return None
        await self._habits.deactivate(habit_id, user_id)
        return ArchiveResult(archived_habit_id=habit_id, archived_habit_name=habit.name)

    async def by_name(self, user_id: int, name_query: str) -> ArchiveResult | None:
        """Архивация по приблизительному названию — для LLM-коуча.

        Поиск нечувствительный к регистру: ищем сначала точное совпадение,
        потом — привычку, в названии которой содержится запрос. Это покрывает
        случаи когда пользователь говорит «удали бег», а в БД она «Бегать по утрам».
        """
        name_query = (name_query or "").strip().lower()
        if not name_query:
            return None

        habits = await self._habits.list_for_user(user_id, active_only=True)

        # Точное совпадение приоритетнее.
        exact = next((h for h in habits if h.name.lower() == name_query), None)
        target: Habit | None = exact
        if target is None:
            # Подстрока: достаточно если в названии есть запрос или наоборот.
            for h in habits:
                hn = h.name.lower()
                if name_query in hn or hn in name_query:
                    target = h
                    break

        if target is None or target.id is None:
            logger.info("ArchiveHabitUseCase.by_name: no match for %r", name_query)
            return None

        await self._habits.deactivate(target.id, user_id)
        return ArchiveResult(archived_habit_id=target.id, archived_habit_name=target.name)
