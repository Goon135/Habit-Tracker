"""Бизнес-правила геймификации: очки за серию, заголовок уровня."""
from __future__ import annotations

BASE_POINTS = 10
STREAK_BONUS_PER_WEEK = 2

_LEVEL_TITLES: dict[int, str] = {
    1: "Новичок",
    2: "Стажёр",
    3: "Ученик",
    5: "Практик",
    7: "Мастер привычек",
    10: "Гуру",
    15: "Легенда",
    20: "Просветлённый",
}


def calculate_points_for_completion(streak_length: int) -> int:
    """Базовые очки + бонус по 2 очка за каждую полную неделю серии."""
    if streak_length < 0:
        raise ValueError("streak_length must be non-negative")
    return BASE_POINTS + (streak_length // 7) * STREAK_BONUS_PER_WEEK


def get_level_title(level: int) -> str:
    title = "Новичок"
    for threshold in sorted(_LEVEL_TITLES):
        if level >= threshold:
            title = _LEVEL_TITLES[threshold]
    return title
