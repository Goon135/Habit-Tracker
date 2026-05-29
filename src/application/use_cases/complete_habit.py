"""Use case: отметить выполнение привычки за сегодня.

Это самый "богатый" use case: пишет лог, считает streak, начисляет очки,
выдаёт достижения. Вся бизнес-логика — в domain.services и value objects,
здесь только оркестрация.

С поддержкой количественных привычек (#2): можно передать `value` — для
обычной булевой привычки value игнорируется, для количественной (с
target_value) добавляется к уже накопленному значению за день.
"""
from __future__ import annotations

from datetime import date

from src.application.dto.dtos import CompletionResultDTO
from src.domain.entities.achievement import Achievement
from src.domain.entities.habit_log import HabitLog
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import AchievementRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.achievements_catalog import (
    find_unlocked_count_achievements,
    find_unlocked_streak_achievements,
)
from src.domain.services.gamification import (
    calculate_points_for_completion,
    get_level_title,
)
from src.domain.value_objects.streak import Streak


class CompleteHabitUseCase:
    def __init__(
        self,
        users: UserRepository,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        achievements: AchievementRepository,
    ) -> None:
        self._users = users
        self._habits = habits
        self._logs = habit_logs
        self._achievements = achievements

    async def execute(
        self,
        user_id: int,
        habit_id: int,
        today: date | None = None,
        value: float | None = None,
    ) -> CompletionResultDTO:
        today = today or date.today()

        # Нужна сама привычка, чтобы понять — количественная или булевая.
        habit = await self._habits.get(habit_id)
        if habit is None or habit.user_id != user_id:
            raise RuntimeError(f"habit {habit_id} not found for user {user_id}")

        # Для количественных: накапливаем value за день (если уже есть лог).
        if habit.is_quantitative:
            added = float(value) if value is not None else 0.0
            existing = await self._logs.get_for_date(habit_id, today)
            current_total = (existing.value if existing else 0.0) + added
            completed = habit.is_completed(current_total)
            progress = habit.progress_ratio(current_total)
            log_value = current_total
        else:
            # Булевая: completed=True, value=1.0.
            log_value = 1.0
            current_total = 1.0
            completed = True
            progress = 1.0

        # 1. Логируем выполнение.
        await self._logs.upsert(
            HabitLog(
                habit_id=habit_id,
                user_id=user_id,
                log_date=today,
                completed=completed,
                value=log_value,
            )
        )

        # 2. Пересчитываем streak (по completed-дням).
        completed_dates = await self._logs.list_completed_dates(habit_id)
        streak = Streak.calculate(completed_dates, today)

        # 3. Начисляем очки только если привычка фактически выполнена.
        # Иначе пользователь, отмечая «выпил 0.5 л из 3 л», не должен получать очки —
        # иначе можно нафармить очков частичными отметками.
        points = 0
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        if completed:
            points = calculate_points_for_completion(streak.length)
            user.add_points(points)
            await self._users.save(user)

        # 4. Достижения — только при полном выполнении.
        new_all: list = []
        if completed:
            earned_codes = await self._achievements.list_codes_for_user(user_id)
            new_streak = find_unlocked_streak_achievements(streak.length, earned_codes)
            active_habits = await self._habits.list_for_user(user_id, active_only=True)
            new_count = find_unlocked_count_achievements(len(active_habits), earned_codes)

            new_all = new_streak + new_count
            for ach_def in new_all:
                await self._achievements.grant(
                    Achievement(
                        user_id=user_id,
                        code=ach_def.code,
                        title=ach_def.title,
                        description=ach_def.description,
                    )
                )

        return CompletionResultDTO(
            streak=streak.length,
            points_earned=points,
            total_points=user.points,
            level=user.level,
            level_title=get_level_title(user.level),
            new_achievements=[
                {"title": a.title, "desc": a.description} for a in new_all
            ],
            current_value=current_total,
            target_value=habit.target_value,
            unit=habit.unit,
            progress_ratio=progress,
            completed=completed,
        )
