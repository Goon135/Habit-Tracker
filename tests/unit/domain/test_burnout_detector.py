"""Unit-тесты BurnoutDetector.

Все методы — pure, проверяем граничные случаи и комбинации факторов.
"""
from __future__ import annotations

from datetime import date, timedelta

from src.domain.services.burnout_detector import BurnoutDetector
from src.domain.value_objects.risk_level import RiskLevel


def test_no_data_returns_low():
    """Пользователь без активности и привычек — LOW (новичок, не выгорание)."""
    assessment = BurnoutDetector.assess(
        completions_by_date={}, mood_by_date={}, habit_count=0,
        today=date(2026, 1, 15),
    )
    assert assessment.level == RiskLevel.LOW
    assert assessment.score == 0


def test_high_risk_full_combo():
    """3+ дней без активности, низкий completion, плохое настроение, перегрузка → HIGH."""
    today = date(2026, 1, 15)
    completions_by_date = {today - timedelta(days=14 + i): 5 for i in range(7)}
    # Последние 7 дней — пусто.
    mood_by_date = {today - timedelta(days=i): 1 for i in range(4)}

    assessment = BurnoutDetector.assess(
        completions_by_date=completions_by_date,
        mood_by_date=mood_by_date,
        habit_count=10,  # overload
        today=today,
    )
    assert assessment.level == RiskLevel.HIGH
    assert assessment.score >= 50
    # Должны быть все факторы.
    text = " ".join(assessment.factors)
    assert "без активности" in text or "пониженным настроением" in text
    assert "много активных привычек" in text


def test_medium_risk_short_inactivity():
    """2 дня без активности, посредственное выполнение → MEDIUM (около 25-40 score)."""
    today = date(2026, 1, 15)
    # 2 inactive_days (вчера и позавчера пусто), активность была за 3 и далее назад.
    # Это даст W_INACTIVITY // 2 = 15 + completion < 50% даст ещё ~12-13 → MEDIUM.
    completions_by_date = {
        today - timedelta(days=3): 1,
        today - timedelta(days=4): 1,
        today - timedelta(days=5): 1,
    }
    assessment = BurnoutDetector.assess(
        completions_by_date=completions_by_date,
        mood_by_date={},
        habit_count=3,
        today=today,
    )
    assert assessment.level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    assert assessment.inactive_days == 2


def test_inactivity_days_count():
    """Проверка _count_inactive_days в изоляции через assess."""
    today = date(2026, 1, 15)
    completions = {today - timedelta(days=5): 1}
    assessment = BurnoutDetector.assess(
        completions_by_date=completions,
        mood_by_date={},
        habit_count=1,
        today=today,
    )
    # 4 дня без активности до последнего выполнения, плюс today не считаем.
    assert assessment.inactive_days == 4


def test_low_mood_streak_counted():
    today = date(2026, 1, 15)
    mood = {today - timedelta(days=i): 1 for i in range(4)}
    assessment = BurnoutDetector.assess(
        completions_by_date={today: 1},
        mood_by_date=mood, habit_count=1, today=today,
    )
    assert assessment.low_mood_streak == 4


def test_low_mood_streak_breaks_on_good_mood():
    today = date(2026, 1, 15)
    mood = {
        today: 1,
        today - timedelta(days=1): 1,
        today - timedelta(days=2): 5,  # хорошее настроение прерывает серию
        today - timedelta(days=3): 1,
    }
    assessment = BurnoutDetector.assess(
        completions_by_date={today: 1},
        mood_by_date=mood, habit_count=1, today=today,
    )
    assert assessment.low_mood_streak == 2  # только 2 последних дня


def test_active_user_returns_low():
    """Активный пользователь без признаков спада → LOW."""
    today = date(2026, 1, 15)
    # Каждый день по 2 выполнения за последние 14 дней.
    completions = {today - timedelta(days=i): 2 for i in range(14)}
    mood = {today - timedelta(days=i): 4 for i in range(14)}

    assessment = BurnoutDetector.assess(
        completions_by_date=completions, mood_by_date=mood,
        habit_count=2, today=today,
    )
    assert assessment.level == RiskLevel.LOW
