"""Use case: архивирование просроченных целей (#6).

Запускается раз в сутки планировщиком. Находит цели с истёкшим end_date
и деактивирует их. Не удаляем — данные остаются для статистики и истории.

Возвращает список заархивированных целей, чтобы планировщик мог уведомить
пользователей.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.application.interfaces.external import Notifier
from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository


@dataclass(frozen=True)
class ArchivedGoalDTO:
    user_id: int
    name: str
    completion_rate: float  # доля выполнения, [0..1]
    total_days: int
    completed_days: int


class ArchiveExpiredGoalsUseCase:
    def __init__(
        self,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        notifier: Notifier | None = None,
    ) -> None:
        self._habits = habits
        self._logs = habit_logs
        self._notifier = notifier

    async def execute(self, today: date | None = None) -> list[ArchivedGoalDTO]:
        today = today or date.today()
        expired = await self._habits.list_expired_goals(today)
        archived: list[ArchivedGoalDTO] = []
        for goal in expired:
            stats = await self._summarize(goal, today)
            goal.deactivate()
            await self._habits.update(goal)
            archived.append(stats)
            if self._notifier:
                await self._notify_user(goal, stats)
        return archived

    async def _summarize(self, goal: Habit, today: date) -> ArchivedGoalDTO:
        # Длительность цели от created_at до end_date.
        start = goal.created_at.date()
        end = goal.end_date or today
        total_days = max((end - start).days + 1, 1)
        completed_dates = await self._logs.list_completed_dates(goal.id)
        completed_in_range = [d for d in completed_dates if start <= d <= end]
        return ArchivedGoalDTO(
            user_id=goal.user_id,
            name=goal.name,
            completion_rate=len(completed_in_range) / total_days,
            total_days=total_days,
            completed_days=len(completed_in_range),
        )

    async def _notify_user(self, goal: Habit, stats: ArchivedGoalDTO) -> None:
        rate = int(stats.completion_rate * 100)
        if rate >= 80:
            emoji = "🏆"
            verdict = "Отличный результат — цель достигнута!"
        elif rate >= 50:
            emoji = "💪"
            verdict = "Хорошая работа, есть прогресс."
        else:
            emoji = "📊"
            verdict = "Не сложилось в этот раз — ничего, попробуем ещё."
        text = (
            f"{emoji} Срок цели «{goal.name}» истёк.\n"
            f"Выполнено: {stats.completed_days} из {stats.total_days} дней ({rate}%).\n"
            f"{verdict}"
        )
        try:
            await self._notifier.send_text(goal.user_id, text)
        except Exception:
            # Уведомление — best-effort, не валим архивацию из-за сетевой ошибки.
            pass
