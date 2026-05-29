"""Streak.calculate — чистая функция, тестируется без моков и БД."""
from datetime import date, timedelta

from src.domain.value_objects.streak import Streak


def test_empty_history_returns_zero():
    s = Streak.calculate([], today=date(2026, 5, 23))
    assert s.length == 0
    assert s.last_completion is None


def test_three_consecutive_days_ending_today():
    today = date(2026, 5, 23)
    dates = [today, today - timedelta(days=1), today - timedelta(days=2)]
    s = Streak.calculate(dates, today=today)
    assert s.length == 3
    assert s.last_completion == today


def test_streak_with_yesterday_as_last_still_valid():
    """Если последнее выполнение было вчера — серия живёт, у пользователя ещё есть сегодня."""
    today = date(2026, 5, 23)
    yesterday = today - timedelta(days=1)
    dates = [yesterday, yesterday - timedelta(days=1)]
    s = Streak.calculate(dates, today=today)
    assert s.length == 2


def test_gap_breaks_streak():
    today = date(2026, 5, 23)
    # Сегодня + 3 дня назад + 4 дня назад — между ними пропуск.
    dates = [today, today - timedelta(days=3), today - timedelta(days=4)]
    s = Streak.calculate(dates, today=today)
    assert s.length == 1


def test_old_completion_resets_streak():
    today = date(2026, 5, 23)
    dates = [today - timedelta(days=5)]
    s = Streak.calculate(dates, today=today)
    assert s.length == 0
    assert s.last_completion == today - timedelta(days=5)


def test_duplicates_are_deduplicated():
    today = date(2026, 5, 23)
    dates = [today, today, today - timedelta(days=1), today - timedelta(days=1)]
    s = Streak.calculate(dates, today=today)
    assert s.length == 2
