"""Аналитический сервис — считает факты из истории логов и настроений.

Принципиально pure: на вход даты + значения, на выход — числа.
Никаких репозиториев, никакого I/O, легко покрывается unit-тестами.

Это «честная» часть AI Insight Engine (фича #1): сначала считаем правилами,
потом LLM просто переводит цифры в человеческий текст. Если LLM упадёт —
числа останутся.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta


# Дни недели (как в datetime: Monday=0).
_WEEKDAY_NAMES_RU = [
    "понедельник", "вторник", "среда", "четверг",
    "пятница", "суббота", "воскресенье",
]


@dataclass(frozen=True)
class WeekdayStats:
    """Распределение completion по дням недели."""
    # weekday → completion_rate (0..1)
    rates: dict[int, float] = field(default_factory=dict)

    @property
    def best_weekday(self) -> int | None:
        if not self.rates:
            return None
        return max(self.rates.items(), key=lambda kv: kv[1])[0]

    @property
    def worst_weekday(self) -> int | None:
        if not self.rates:
            return None
        return min(self.rates.items(), key=lambda kv: kv[1])[0]

    def name(self, weekday: int) -> str:
        return _WEEKDAY_NAMES_RU[weekday]


@dataclass(frozen=True)
class MoodCorrelation:
    """Корреляция настроения и выполнения привычек."""
    avg_completion_after_low_mood: float    # 0..1, completion после плохого настроения
    avg_completion_after_high_mood: float   # 0..1
    delta_pct: float                        # разница в процентах (отрицательная если low хуже)
    samples_low: int
    samples_high: int

    @property
    def is_significant(self) -> bool:
        """Эвристика для интерпретации: считаем разницу значимой при |delta| >= 15%
        и хотя бы 3 наблюдения в каждой группе."""
        return (
            abs(self.delta_pct) >= 15.0
            and self.samples_low >= 3
            and self.samples_high >= 3
        )


@dataclass(frozen=True)
class ActivityHeatmap:
    """Тепловая карта активности за N последних дней.

    Хранится как list[list[int]] по weekday × неделям, значение — кол-во
    выполненных привычек в этот день. Удобно для отрисовки в текстовом виде.
    """
    # weeks[i][weekday] = count
    weeks: list[list[int]]
    start_date: date
    max_value: int


@dataclass(frozen=True)
class AnalyticsReport:
    """Сводный отчёт за период."""
    period_days: int
    total_completions: int
    total_expected: int
    completion_rate: float                   # 0..1
    current_avg_streak: float                # средний streak по активным привычкам
    weekday_stats: WeekdayStats
    mood_correlation: MoodCorrelation | None  # None если нет данных
    heatmap: ActivityHeatmap
    risk_factors: list[str] = field(default_factory=list)  # для interpretation
    declining_trend: bool = False  # сравнение последней недели с предыдущей


class AnalyticsService:
    """Stateless сервис. Все методы — pure.

    Расчёт намеренно простой и объяснимый: для дипломной защиты важно уметь
    в любой момент сказать «вот формула, вот что она считает».
    """

    @staticmethod
    def weekday_completion_rates(
        completed_dates: list[date],
        expected_per_day: int,
        since: date,
        today: date,
    ) -> WeekdayStats:
        """Доля выполнений по дням недели за период [since, today].

        expected_per_day = кол-во активных привычек: предполагаем, что в день
        пользователь должен выполнить столько привычек, сколько у него есть активных.
        Это упрощение (не учитываем weekly_n / weekdays-расписание), но для
        дипломной аналитики достаточно.
        """
        if expected_per_day <= 0 or today < since:
            return WeekdayStats(rates={})

        # Кол-во дней каждого weekday в периоде.
        days_per_weekday: Counter[int] = Counter()
        d = since
        while d <= today:
            days_per_weekday[d.weekday()] += 1
            d += timedelta(days=1)

        # Кол-во выполнений по weekday.
        completions_per_weekday: Counter[int] = Counter()
        for cd in completed_dates:
            if since <= cd <= today:
                completions_per_weekday[cd.weekday()] += 1

        rates: dict[int, float] = {}
        for wd in range(7):
            total_expected = days_per_weekday[wd] * expected_per_day
            if total_expected == 0:
                continue
            rates[wd] = min(completions_per_weekday[wd] / total_expected, 1.0)

        return WeekdayStats(rates=rates)

    @staticmethod
    def mood_completion_correlation(
        mood_by_date: dict[date, int],
        completions_by_date: dict[date, int],
        expected_per_day: int,
        low_threshold: int = 2,
        high_threshold: int = 4,
    ) -> MoodCorrelation | None:
        """Сравниваем completion СЛЕДУЮЩЕГО дня после плохого vs хорошего настроения.

        Гипотеза: после плохого настроения труднее выполнять — completion падает.
        Возвращаем None если нет данных.
        """
        if expected_per_day <= 0 or not mood_by_date:
            return None

        low_completions: list[float] = []
        high_completions: list[float] = []

        for mood_date, score in mood_by_date.items():
            next_day = mood_date + timedelta(days=1)
            done = completions_by_date.get(next_day, 0)
            rate = min(done / expected_per_day, 1.0)
            if score <= low_threshold:
                low_completions.append(rate)
            elif score >= high_threshold:
                high_completions.append(rate)

        if not low_completions or not high_completions:
            return None

        avg_low = sum(low_completions) / len(low_completions)
        avg_high = sum(high_completions) / len(high_completions)
        # delta_pct = разница в процентных пунктах * 100. Отрицательная — после low хуже.
        delta_pct = (avg_low - avg_high) * 100

        return MoodCorrelation(
            avg_completion_after_low_mood=avg_low,
            avg_completion_after_high_mood=avg_high,
            delta_pct=delta_pct,
            samples_low=len(low_completions),
            samples_high=len(high_completions),
        )

    @staticmethod
    def build_heatmap(
        completions_by_date: dict[date, int],
        weeks: int = 8,
        today: date | None = None,
    ) -> ActivityHeatmap:
        """Heatmap последних N недель.

        Каждая «неделя» — список 7 чисел (Mon..Sun), значение — кол-во
        выполненных привычек в этот день. Старт — Monday недели на (weeks-1)
        недель назад от today.
        """
        today = today or date.today()
        # Понедельник текущей недели.
        current_monday = today - timedelta(days=today.weekday())
        start = current_monday - timedelta(days=7 * (weeks - 1))

        grid: list[list[int]] = []
        max_value = 0
        for w in range(weeks):
            week_row = []
            for wd in range(7):
                d = start + timedelta(days=7 * w + wd)
                if d > today:
                    week_row.append(0)
                else:
                    val = completions_by_date.get(d, 0)
                    week_row.append(val)
                    if val > max_value:
                        max_value = val
            grid.append(week_row)

        return ActivityHeatmap(weeks=grid, start_date=start, max_value=max_value)

    @staticmethod
    def detect_declining_trend(
        completions_by_date: dict[date, int],
        expected_per_day: int,
        today: date | None = None,
    ) -> bool:
        """Снижается ли completion: последние 7 дней vs предыдущие 7 дней.

        Возвращает True, если последняя неделя хуже предыдущей хотя бы на 20%.
        """
        if expected_per_day <= 0:
            return False
        today = today or date.today()
        last_week_start = today - timedelta(days=6)
        prev_week_start = today - timedelta(days=13)
        prev_week_end = today - timedelta(days=7)

        last = sum(
            completions_by_date.get(last_week_start + timedelta(days=i), 0)
            for i in range(7)
        )
        prev = sum(
            completions_by_date.get(prev_week_start + timedelta(days=i), 0)
            for i in range(7)
        )

        if prev == 0:
            return False  # не с чем сравнивать
        decline = (prev - last) / prev
        return decline >= 0.20

    @staticmethod
    def render_heatmap_ascii(heatmap: ActivityHeatmap) -> str:
        """Отрисовка heatmap в текст: используется в /insights и /stats."""
        if heatmap.max_value == 0:
            return "(нет данных для heatmap)"

        # 5 уровней: пусто, мало, средне, много, максимум.
        symbols = ["·", "▁", "▃", "▆", "█"]

        def cell(v: int) -> str:
            if v == 0:
                return symbols[0]
            ratio = v / heatmap.max_value
            if ratio < 0.25:
                return symbols[1]
            if ratio < 0.5:
                return symbols[2]
            if ratio < 0.75:
                return symbols[3]
            return symbols[4]

        lines = ["    Пн Вт Ср Чт Пт Сб Вс"]
        for i, week in enumerate(heatmap.weeks):
            week_start = heatmap.start_date + timedelta(days=7 * i)
            label = week_start.strftime("%d.%m")
            cells = "  ".join(cell(v) for v in week)
            lines.append(f"{label}  {cells}")
        return "\n".join(lines)
