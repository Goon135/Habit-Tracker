"""Use cases для burnout-detection (#2) и recovery mode (#3).

AssessBurnoutRiskUseCase — синхронная оценка риска по правилам.
ToggleRecoveryModeUseCase — вход/выход из режима anti-burnout.
CheckBurnoutAndProposeRecoveryUseCase — фоновая проверка планировщиком.

Recovery mode применяется тремя слоями:
1. User.is_in_recovery() — флаг, доступен везде через User entity.
2. CoachReply подсматривает в is_in_recovery() и подменяет стиль на GENTLE.
3. SendReminders подсматривает и НЕ шлёт напоминания.
4. GetTodayProgress снижает target_value на 30% при показе (визуально, в БД не меняем).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from src.application.dto.analytics_dtos import (
    BurnoutAssessmentDTO,
    RecoveryStateDTO,
)
from src.application.interfaces.external import Notifier
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import MoodRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.burnout_detector import BurnoutDetector
from src.domain.value_objects.risk_level import RiskLevel

logger = logging.getLogger(__name__)


# Длительность recovery по умолчанию — 3 дня.
DEFAULT_RECOVERY_DAYS = 3

# Не предлагать recovery чаще, чем раз в N дней. Чтобы пользователь не получал
# одно и то же предложение каждый день.
RECOVERY_OFFER_COOLDOWN_DAYS = 7


class AssessBurnoutRiskUseCase:
    """Считает текущий риск burnout. Используется в /recovery и при /insights."""

    def __init__(
        self,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        moods: MoodRepository,
    ) -> None:
        self._habits = habits
        self._logs = habit_logs
        self._moods = moods

    async def execute(self, user_id: int, today: date | None = None) -> BurnoutAssessmentDTO:
        today = today or date.today()
        since = today - timedelta(days=29)

        habits = await self._habits.list_for_user(user_id, active_only=True)
        habit_count = len(habits)
        logs = await self._logs.list_for_user_in_range(user_id, since, today)
        completed_logs = [log for log in logs if log.completed]
        completions_by_date: dict[date, int] = {}
        for log in completed_logs:
            completions_by_date[log.log_date] = completions_by_date.get(log.log_date, 0) + 1

        mood_entries = await self._moods.list_for_user(user_id, since=since)
        mood_by_date = {m.entry_date: m.score for m in mood_entries}

        assessment = BurnoutDetector.assess(
            completions_by_date=completions_by_date,
            mood_by_date=mood_by_date,
            habit_count=habit_count,
            today=today,
        )

        return BurnoutAssessmentDTO(
            level=assessment.level.value,
            level_emoji=assessment.level.emoji,
            level_label=assessment.level.label,
            score=assessment.score,
            factors=list(assessment.factors),
            inactive_days=assessment.inactive_days,
            completion_rate_7d=assessment.completion_rate_7d,
        )


class ToggleRecoveryModeUseCase:
    """Включает/выключает recovery mode для пользователя."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def enter(
        self, user_id: int, days: int = DEFAULT_RECOVERY_DAYS, today: date | None = None,
    ) -> RecoveryStateDTO:
        today = today or date.today()
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        until = today + timedelta(days=days)
        user.enter_recovery(until)
        await self._users.save(user)
        return RecoveryStateDTO(
            is_active=True, until=until, days_left=days,
            started_at=user.recovery_started_at.date() if user.recovery_started_at else today,
        )

    async def exit(self, user_id: int) -> RecoveryStateDTO:
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        user.exit_recovery()
        await self._users.save(user)
        return RecoveryStateDTO(is_active=False)

    async def status(self, user_id: int, today: date | None = None) -> RecoveryStateDTO:
        today = today or date.today()
        user = await self._users.get(user_id)
        if user is None or not user.is_in_recovery(today):
            return RecoveryStateDTO(is_active=False)
        days_left = (user.recovery_until - today).days
        return RecoveryStateDTO(
            is_active=True,
            until=user.recovery_until,
            days_left=days_left,
            started_at=user.recovery_started_at.date() if user.recovery_started_at else None,
        )


class CheckBurnoutAndProposeRecoveryUseCase:
    """Фоновая ежедневная задача: проверяет всех пользователей, при HIGH-риске
    шлёт мягкое предложение войти в recovery mode.

    Идемпотентна: при повторном вызове в тот же день ничего не делает
    (защита через recovery_started_at + cooldown). Также не предлагает,
    если пользователь уже в recovery.
    """

    def __init__(
        self,
        users: UserRepository,
        assess: AssessBurnoutRiskUseCase,
        notifier: Notifier | None = None,
    ) -> None:
        self._users = users
        self._assess = assess
        self._notifier = notifier

    async def execute(self, today: date | None = None) -> int:
        """Возвращает количество отправленных предложений."""
        today = today or date.today()
        users = await self._users.list_all_with_reminder()
        offered = 0
        for user in users:
            if user.is_in_recovery(today):
                continue
            # Cooldown: не предлагать, если recovery_started_at был недавно.
            if user.recovery_started_at is not None:
                days_since = (today - user.recovery_started_at.date()).days
                if days_since < RECOVERY_OFFER_COOLDOWN_DAYS:
                    continue
            try:
                assessment = await self._assess.execute(user.id, today=today)
            except Exception as exc:
                logger.warning("burnout assessment failed for %s: %r", user.id, exc)
                continue
            if assessment.level != RiskLevel.HIGH.value:
                continue
            if self._notifier:
                await self._notify(user.id, assessment)
                offered += 1
        return offered

    async def _notify(self, user_id: int, assessment: BurnoutAssessmentDTO) -> None:
        factor_text = ""
        if assessment.factors:
            factor_text = "\n\nЗаметил:\n" + "\n".join(f"• {f}" for f in assessment.factors[:3])
        text = (
            "🌿 Похоже, у тебя сейчас непростой период."
            f"{factor_text}\n\n"
            "Хочешь включить режим восстановления на 3 дня?\n"
            "В этом режиме:\n"
            "• цели снижаются на 30%\n"
            "• напоминания приостанавливаются\n"
            "• коуч переключается на мягкий тон\n\n"
            "Включить: /recovery"
        )
        try:
            await self._notifier.send_text(user_id, text)
        except Exception:
            pass
