"""Детектор риска выгорания / срыва — фичи #2 и #3.

Rule-based система: считаем баллы по нескольким факторам, по сумме баллов
выдаём уровень риска.

Намеренно простая, объяснимая логика. Для дипломной защиты:
> «Мы не используем ML здесь, потому что (а) у нас сотни наблюдений, не тысячи,
>  (б) интерпретируемость важнее точности — пользователю показываем причину,
>  (в) baseline для будущей ML-модели».
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from src.domain.value_objects.risk_level import RiskLevel


@dataclass(frozen=True)
class BurnoutAssessment:
    """Результат оценки риска burnout."""
    level: RiskLevel
    score: int                          # 0..100
    factors: list[str] = field(default_factory=list)  # человеко-читаемые причины
    inactive_days: int = 0              # дней подряд без выполнений
    completion_rate_7d: float = 0.0     # rate за последние 7 дней
    low_mood_streak: int = 0            # дней подряд с настроением <= 2
    habit_count: int = 0


class BurnoutDetector:
    """Stateless. Все методы — pure.

    Пороги выбраны эвристически. Они задокументированы тут и в дипломе —
    можно обосновать «здравым смыслом» и эмпирическими данными из mood-исследований.
    """

    # Веса факторов (макс 100).
    W_INACTIVITY = 30
    W_LOW_COMPLETION = 25
    W_LOW_MOOD = 20
    W_HABIT_OVERLOAD = 15
    W_DECLINING = 10

    @classmethod
    def assess(
        cls,
        completions_by_date: dict[date, int],
        mood_by_date: dict[date, int],
        habit_count: int,
        today: date | None = None,
    ) -> BurnoutAssessment:
        today = today or date.today()

        # Особый случай: пользователь без привычек — это «новичок», а не
        # «выгоревший». Не наказываем баллами. Но если привычки есть, а
        # активности нет — это сигнал тревоги, идём дальше по логике.
        if habit_count == 0:
            return BurnoutAssessment(
                level=RiskLevel.LOW,
                score=0,
                factors=[],
                inactive_days=0,
                completion_rate_7d=0.0,
                low_mood_streak=0,
                habit_count=habit_count,
            )

        # 1. Дни подряд без выполнений.
        inactive = cls._count_inactive_days(completions_by_date, today)

        # 2. Completion rate за последние 7 дней (примерный, через habit_count).
        completion_7d = cls._completion_rate_window(
            completions_by_date, habit_count, days=7, today=today,
        )

        # 3. Серия плохого настроения.
        low_mood = cls._count_low_mood_streak(mood_by_date, today)

        # 4. Перегрузка привычками (субъективный порог 8+).
        overload = habit_count >= 8

        # 5. Снижающийся тренд (последняя неделя хуже предпоследней).
        declining = cls._detect_decline(completions_by_date, habit_count, today)

        # Сумма баллов.
        score = 0
        factors: list[str] = []

        if inactive >= 3:
            score += cls.W_INACTIVITY
            factors.append(f"{inactive} дней без активности")
        elif inactive == 2:
            score += cls.W_INACTIVITY // 2
            factors.append("2 дня без активности")

        if completion_7d < 0.3 and habit_count > 0:
            score += cls.W_LOW_COMPLETION
            factors.append(f"низкое выполнение за неделю ({int(completion_7d * 100)}%)")
        elif completion_7d < 0.5 and habit_count > 0:
            score += cls.W_LOW_COMPLETION // 2

        if low_mood >= 3:
            score += cls.W_LOW_MOOD
            factors.append(f"{low_mood} дней с пониженным настроением")
        elif low_mood == 2:
            score += cls.W_LOW_MOOD // 2

        if overload:
            score += cls.W_HABIT_OVERLOAD
            factors.append(f"много активных привычек ({habit_count})")

        if declining:
            score += cls.W_DECLINING
            factors.append("снижающийся тренд активности")

        # Маппинг суммы в уровень.
        if score >= 50:
            level = RiskLevel.HIGH
        elif score >= 25:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return BurnoutAssessment(
            level=level,
            score=score,
            factors=factors,
            inactive_days=inactive,
            completion_rate_7d=completion_7d,
            low_mood_streak=low_mood,
            habit_count=habit_count,
        )

    # ─────────── Вспомогательные расчёты ───────────

    @staticmethod
    def _count_inactive_days(completions_by_date: dict[date, int], today: date) -> int:
        """Сколько дней подряд (начиная с вчера) не было выполнений."""
        count = 0
        d = today - timedelta(days=1)
        # Не считаем сам "today" — может быть, пользователь ещё успеет сегодня.
        while completions_by_date.get(d, 0) == 0:
            count += 1
            d -= timedelta(days=1)
            if count > 60:  # отсечка на случай новичка без истории
                break
        return count

    @staticmethod
    def _completion_rate_window(
        completions_by_date: dict[date, int],
        habit_count: int,
        days: int,
        today: date,
    ) -> float:
        if habit_count == 0:
            return 0.0
        total_done = 0
        for i in range(days):
            d = today - timedelta(days=i)
            total_done += completions_by_date.get(d, 0)
        return min(total_done / (habit_count * days), 1.0)

    @staticmethod
    def _count_low_mood_streak(mood_by_date: dict[date, int], today: date) -> int:
        """Сколько дней подряд (от today назад) настроение было <= 2."""
        count = 0
        d = today
        while d in mood_by_date and mood_by_date[d] <= 2:
            count += 1
            d -= timedelta(days=1)
            if count > 30:
                break
        return count

    @staticmethod
    def _detect_decline(
        completions_by_date: dict[date, int],
        habit_count: int,
        today: date,
    ) -> bool:
        if habit_count == 0:
            return False
        last_week = sum(
            completions_by_date.get(today - timedelta(days=i), 0)
            for i in range(7)
        )
        prev_week = sum(
            completions_by_date.get(today - timedelta(days=i + 7), 0)
            for i in range(7)
        )
        if prev_week == 0:
            return False
        return (prev_week - last_week) / prev_week >= 0.20
