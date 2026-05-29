"""Unit-тесты AnalyticsService.

Сервис чисто-функциональный — даём ему данные, проверяем числа.
"""
from __future__ import annotations

from datetime import date, timedelta

from src.domain.services.analytics_service import AnalyticsService


def test_weekday_rates_empty_returns_zeros():
    """Без выполнений — каждый weekday получает 0% (а не отсутствует)."""
    today = date(2026, 1, 31)  # суббота
    since = today - timedelta(days=29)
    stats = AnalyticsService.weekday_completion_rates(
        completed_dates=[], expected_per_day=2, since=since, today=today,
    )
    # Все 7 дней недели присутствуют в периоде, у каждого 0%.
    assert len(stats.rates) == 7
    assert all(rate == 0.0 for rate in stats.rates.values())


def test_weekday_rates_finds_best_and_worst():
    # 2 привычки/день, 14 дней. В понедельники — 2 раза по 2 (100%),
    # в пятницы — 1 раз по 1 (50%), в остальные дни — 0.
    today = date(2026, 1, 11)  # воскресенье
    since = today - timedelta(days=13)  # понедельник 2 недели назад
    completed: list[date] = []
    d = since
    while d <= today:
        if d.weekday() == 0:  # понедельник
            completed += [d, d]
        elif d.weekday() == 4:  # пятница
            completed += [d]
        d += timedelta(days=1)

    stats = AnalyticsService.weekday_completion_rates(
        completed_dates=completed, expected_per_day=2, since=since, today=today,
    )
    assert stats.best_weekday == 0  # понедельник
    assert stats.worst_weekday is not None
    # Понедельник — 100%, пятница — 50%, остальные — 0%.
    assert stats.rates[0] == 1.0
    assert stats.rates[4] == 0.5
    assert stats.name(0) == "понедельник"


def test_mood_correlation_returns_none_without_high_mood():
    today = date(2026, 1, 31)
    mood = {today - timedelta(days=i): 2 for i in range(5)}  # только плохое
    completions = {today - timedelta(days=i): 1 for i in range(5)}

    result = AnalyticsService.mood_completion_correlation(
        mood_by_date=mood, completions_by_date=completions, expected_per_day=2,
    )
    assert result is None  # нет high samples


def test_mood_correlation_detects_negative_effect():
    """Сценарий: после плохого настроения выполнение ниже."""
    today = date(2026, 1, 31)
    # 4 «плохих» дня и 4 «хороших», по 2 ожидаемых привычки в день.
    mood: dict[date, int] = {}
    completions: dict[date, int] = {}
    for i in range(4):
        bad_day = today - timedelta(days=i * 2)
        mood[bad_day] = 1  # плохо
        # На следующий день — 0 выполнений.
        completions[bad_day + timedelta(days=1)] = 0
    for i in range(4):
        good_day = today - timedelta(days=i * 2 + 1)
        mood[good_day] = 5  # хорошо
        # На следующий день — 2 выполнения (полное).
        completions[good_day + timedelta(days=1)] = 2

    corr = AnalyticsService.mood_completion_correlation(
        mood_by_date=mood, completions_by_date=completions, expected_per_day=2,
    )
    assert corr is not None
    assert corr.avg_completion_after_low_mood == 0.0
    assert corr.avg_completion_after_high_mood == 1.0
    assert corr.delta_pct == -100.0  # сильно хуже после плохого
    assert corr.is_significant


def test_heatmap_contains_correct_max_value():
    today = date(2026, 1, 11)  # воскресенье
    completions = {
        today: 5,
        today - timedelta(days=1): 3,
        today - timedelta(days=8): 7,
    }
    hm = AnalyticsService.build_heatmap(completions, weeks=4, today=today)
    assert hm.max_value == 7
    # Воскресенье (последний день) последней недели — это today.
    last_week = hm.weeks[-1]
    assert last_week[6] == 5  # воскресенье


def test_heatmap_ascii_not_empty_when_data():
    today = date(2026, 1, 11)
    completions = {today: 3}
    hm = AnalyticsService.build_heatmap(completions, weeks=2, today=today)
    text = AnalyticsService.render_heatmap_ascii(hm)
    assert "Пн Вт Ср" in text
    assert "█" in text  # символ для max-cell


def test_declining_trend_detects_drop():
    today = date(2026, 1, 14)  # среда
    # Предыдущая неделя — 10 выполнений, последняя — 3 (-70%).
    completions: dict[date, int] = {}
    for i in range(7):
        completions[today - timedelta(days=i + 7)] = 2 if i % 2 else 1
    # Последняя неделя — намного меньше.
    completions[today - timedelta(days=2)] = 1

    declining = AnalyticsService.detect_declining_trend(
        completions, expected_per_day=2, today=today,
    )
    assert declining is True


def test_declining_trend_false_when_stable():
    today = date(2026, 1, 14)
    completions = {today - timedelta(days=i): 2 for i in range(14)}
    declining = AnalyticsService.detect_declining_trend(
        completions, expected_per_day=2, today=today,
    )
    assert declining is False
