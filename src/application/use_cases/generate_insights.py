"""Use case: сгенерировать инсайт по аналитике пользователя (#1).

Архитектура двухслойная:
1. Считаем все факты через AnalyticsService (pure-Python, объяснимо).
2. LLM формулирует текст инсайта. Если LLM недоступен/упал — собираем текст
   шаблоном из тех же фактов.

Это компромисс из вопроса пользователя: «правила + LLM формулирует».
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from src.application.dto.analytics_dtos import InsightDTO
from src.application.interfaces.ai_services import LLMInsightFormatter
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import MoodRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.analytics_service import AnalyticsService

logger = logging.getLogger(__name__)


# Период для анализа.
ANALYSIS_DAYS = 30
HEATMAP_WEEKS = 8


class GenerateInsightsUseCase:
    def __init__(
        self,
        users: UserRepository,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        moods: MoodRepository,
        formatter: LLMInsightFormatter | None = None,
    ) -> None:
        self._users = users
        self._habits = habits
        self._logs = habit_logs
        self._moods = moods
        self._formatter = formatter

    async def execute(self, user_id: int, today: date | None = None) -> InsightDTO | None:
        """Считаем инсайт. Возвращаем None, если данных слишком мало.

        Минимум для осмысленного инсайта: хотя бы 1 активная привычка
        и хотя бы 3 дня истории.
        """
        today = today or date.today()
        habits = await self._habits.list_for_user(user_id, active_only=True)
        if not habits:
            return None

        since = today - timedelta(days=ANALYSIS_DAYS - 1)
        logs = await self._logs.list_for_user_in_range(user_id, since, today)
        if len(logs) < 3:
            return None

        # Агрегации.
        completed_logs = [log for log in logs if log.completed]
        completions_by_date: dict[date, int] = {}
        for log in completed_logs:
            completions_by_date[log.log_date] = completions_by_date.get(log.log_date, 0) + 1

        all_completed_dates = [log.log_date for log in completed_logs]
        habit_count = len(habits)

        # 1. По дням недели.
        weekday_stats = AnalyticsService.weekday_completion_rates(
            all_completed_dates, expected_per_day=habit_count, since=since, today=today,
        )

        # 2. Корреляция настроения.
        moods = await self._moods.list_for_user(user_id, since=since)
        mood_by_date = {m.entry_date: m.score for m in moods}
        mood_corr = AnalyticsService.mood_completion_correlation(
            mood_by_date, completions_by_date, expected_per_day=habit_count,
        )

        # 3. Heatmap.
        heatmap = AnalyticsService.build_heatmap(
            completions_by_date, weeks=HEATMAP_WEEKS, today=today,
        )
        heatmap_ascii = AnalyticsService.render_heatmap_ascii(heatmap)

        # 4. Declining trend.
        declining = AnalyticsService.detect_declining_trend(
            completions_by_date, expected_per_day=habit_count, today=today,
        )

        # Общая completion rate за период.
        total_expected = habit_count * ANALYSIS_DAYS
        total_done = len(completed_logs)
        completion_rate = min(total_done / total_expected, 1.0) if total_expected else 0.0

        # Собираем факты для LLM-форматтера.
        facts: dict = {
            "период анализа": f"{ANALYSIS_DAYS} дней",
            "общий % выполнения": f"{int(completion_rate * 100)}%",
            "всего выполнений": total_done,
        }
        best_day_name: str | None = None
        worst_day_name: str | None = None
        best_day_rate: float | None = None
        if weekday_stats.rates and weekday_stats.best_weekday is not None:
            best_day_name = weekday_stats.name(weekday_stats.best_weekday)
            worst_day_name = weekday_stats.name(weekday_stats.worst_weekday)
            best_day_rate = weekday_stats.rates[weekday_stats.best_weekday]
            worst_day_rate = weekday_stats.rates[weekday_stats.worst_weekday]
            facts["лучший день недели"] = (
                f"{best_day_name} ({int(best_day_rate * 100)}%)"
            )
            facts["худший день недели"] = (
                f"{worst_day_name} ({int(worst_day_rate * 100)}%)"
            )

        if mood_corr and mood_corr.is_significant:
            facts["после плохого настроения выполнение"] = (
                f"{int(mood_corr.avg_completion_after_low_mood * 100)}%"
            )
            facts["после хорошего настроения выполнение"] = (
                f"{int(mood_corr.avg_completion_after_high_mood * 100)}%"
            )
            facts["разница"] = (
                f"{int(abs(mood_corr.delta_pct))}% "
                f"({'хуже' if mood_corr.delta_pct < 0 else 'лучше'} после спада)"
            )

        if declining:
            facts["тренд"] = "снижается (последняя неделя хуже предыдущей)"

        # Форматируем текст.
        llm_text = ""
        if self._formatter is not None:
            try:
                llm_text = await self._formatter.format_insight(facts)
            except Exception as exc:
                logger.warning("insight formatter failed: %r", exc)

        if llm_text:
            summary_text = llm_text
            formatted_by_llm = True
        else:
            summary_text = self._fallback_text(facts, declining)
            formatted_by_llm = False

        # Сохраняем timestamp последнего инсайта (для ratelimit).
        user = await self._users.get(user_id)
        if user is not None:
            user.last_insight_at = datetime.utcnow()
            await self._users.save(user)

        return InsightDTO(
            period_days=ANALYSIS_DAYS,
            completion_rate=completion_rate,
            total_completions=total_done,
            best_weekday_name=best_day_name,
            worst_weekday_name=worst_day_name,
            best_weekday_rate=best_day_rate,
            mood_delta_pct=mood_corr.delta_pct if mood_corr and mood_corr.is_significant else None,
            has_significant_mood_correlation=bool(mood_corr and mood_corr.is_significant),
            heatmap_ascii=heatmap_ascii,
            declining_trend=declining,
            summary_text=summary_text,
            formatted_by_llm=formatted_by_llm,
        )

    @staticmethod
    def _fallback_text(facts: dict, declining: bool) -> str:
        """Сборка текста без LLM. Используется если LLM упал или отключён."""
        parts: list[str] = []
        rate = facts.get("общий % выполнения")
        if rate:
            parts.append(f"За последний месяц общий % выполнения — {rate}.")

        best_day = facts.get("лучший день недели")
        worst_day = facts.get("худший день недели")
        if best_day and worst_day:
            parts.append(
                f"Лучше всего получается в {best_day}, "
                f"хуже всего — в {worst_day}."
            )

        mood = facts.get("разница")
        if mood:
            parts.append(f"Настроение влияет: разница {mood}.")

        if declining:
            parts.append("⚠️ Последняя неделя слабее предыдущей — присмотрись.")

        if not parts:
            parts.append("Данных пока маловато для содержательного инсайта.")
        return " ".join(parts)
