"""Use cases для настроения и анализа корреляций."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from src.domain.entities.mood_entry import MoodEntry
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import MoodRepository


class LogMoodUseCase:
    def __init__(self, moods: MoodRepository) -> None:
        self._moods = moods

    async def execute(self, user_id: int, score: int, note: str | None = None) -> None:
        entry = MoodEntry(user_id=user_id, entry_date=date.today(), score=score, note=note)
        await self._moods.add(entry)


@dataclass(frozen=True)
class HabitMoodInsight:
    habit_name: str
    avg_mood_when_done: float
    avg_mood_when_skipped: float
    sample_size: int
    delta: float  # = avg_done - avg_skipped


class MoodCorrelationUseCase:
    """В дни, когда привычка X выполнена vs пропущена — среднее настроение."""

    def __init__(
        self,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        moods: MoodRepository,
    ) -> None:
        self._habits = habits
        self._logs = habit_logs
        self._moods = moods

    async def execute(self, user_id: int, days: int = 30) -> list[HabitMoodInsight]:
        since = date.today() - timedelta(days=days)
        mood_entries = await self._moods.list_for_user(user_id, since)
        if len(mood_entries) < 3:
            # Слишком мало данных для каких-либо выводов.
            return []
        mood_by_date: dict[date, int] = {m.entry_date: m.score for m in mood_entries}

        habits = await self._habits.list_for_user(user_id, active_only=True)
        insights: list[HabitMoodInsight] = []

        for h in habits:
            logs = await self._logs.list_for_habit(h.id, since)
            done_by_date: dict[date, bool] = {log.log_date: log.completed for log in logs}

            mood_done: list[int] = []
            mood_skipped: list[int] = []
            for d, mood in mood_by_date.items():
                if d in done_by_date:
                    (mood_done if done_by_date[d] else mood_skipped).append(mood)
                else:
                    # День без записи о привычке = пропуск.
                    mood_skipped.append(mood)

            if not mood_done or not mood_skipped:
                continue

            avg_done = sum(mood_done) / len(mood_done)
            avg_skipped = sum(mood_skipped) / len(mood_skipped)
            insights.append(
                HabitMoodInsight(
                    habit_name=h.name,
                    avg_mood_when_done=round(avg_done, 2),
                    avg_mood_when_skipped=round(avg_skipped, 2),
                    sample_size=len(mood_done) + len(mood_skipped),
                    delta=round(avg_done - avg_skipped, 2),
                )
            )

        insights.sort(key=lambda i: abs(i.delta), reverse=True)
        return insights
