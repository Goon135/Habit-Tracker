"""Use case: статус привычек на сегодня + streak'и + прогресс по количественным.

Для количественных привычек подтягиваем текущее значение из лога за сегодня.
Если пользователь в recovery mode (#3) — target_value снижается на 30%
ТОЛЬКО при показе. В БД исходный target не меняется.
"""
from __future__ import annotations

from datetime import date

from src.application.dto.dtos import HabitProgressDTO
from src.domain.repositories.habit_repository import HabitLogRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.streak import Streak


# Сколько процентов от исходного target оставляем в recovery mode.
RECOVERY_TARGET_RATIO = 0.7


class GetTodayProgressUseCase:
    def __init__(
        self,
        habit_logs: HabitLogRepository,
        users: UserRepository | None = None,
    ) -> None:
        self._logs = habit_logs
        self._users = users

    async def execute(self, user_id: int, today: date | None = None) -> list[HabitProgressDTO]:
        today = today or date.today()

        # Проверяем recovery (если репозиторий передан).
        in_recovery = False
        if self._users is not None:
            user = await self._users.get(user_id)
            if user is not None and user.is_in_recovery(today):
                in_recovery = True

        pairs = await self._logs.today_status(user_id, today)

        result: list[HabitProgressDTO] = []
        for habit, completed in pairs:
            completed_dates = await self._logs.list_completed_dates(habit.id)
            streak = Streak.calculate(completed_dates, today)

            current_value = 0.0
            if habit.is_quantitative:
                today_log = await self._logs.get_for_date(habit.id, today)
                current_value = today_log.value if today_log else 0.0
            elif completed:
                current_value = 1.0

            # В recovery mode: снижаем target на 30% (показываем «как будто»).
            display_target = habit.target_value
            if in_recovery and habit.is_quantitative and habit.target_value:
                display_target = habit.target_value * RECOVERY_TARGET_RATIO

            result.append(
                HabitProgressDTO(
                    habit_id=habit.id,
                    name=habit.name,
                    category=habit.category.value,
                    streak=streak.length,
                    completed_today=completed,
                    current_value=current_value,
                    target_value=display_target,
                    unit=habit.unit,
                    is_goal=habit.is_goal,
                    end_date=habit.end_date,
                )
            )
        return result
