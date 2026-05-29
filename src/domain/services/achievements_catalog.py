"""Каталог достижений и логика их выдачи.

Достижения определены декларативно — это упрощает добавление новых и тестирование.
Логика выдачи — чистая функция: принимает контекст, возвращает список новых
достижений (без побочных эффектов).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AchievementDef:
    code: str
    title: str
    description: str


STREAK_ACHIEVEMENTS: list[tuple[int, AchievementDef]] = [
    (3,   AchievementDef("streak_3",   "🔥 Первый огонь",       "Серия 3 дня подряд!")),
    (7,   AchievementDef("streak_7",   "⭐ Недельный марафон",   "Серия 7 дней подряд!")),
    (21,  AchievementDef("streak_21",  "🏆 21 день — привычка!", "Привычка сформирована!")),
    (30,  AchievementDef("streak_30",  "💎 Месяц стабильности",  "Серия 30 дней подряд!")),
    (60,  AchievementDef("streak_60",  "🦾 Несгибаемый",         "Серия 60 дней подряд!")),
    (100, AchievementDef("streak_100", "👑 Легенда",             "Серия 100 дней подряд!")),
]

HABIT_COUNT_ACHIEVEMENTS: list[tuple[int, AchievementDef]] = [
    (1, AchievementDef("habits_1", "🌱 Первый шаг",     "Создана первая привычка!")),
    (3, AchievementDef("habits_3", "🌿 Тройной фокус",  "Три активные привычки!")),
    (5, AchievementDef("habits_5", "🌳 Пятёрка лидера", "Пять активных привычек!")),
]


def find_unlocked_streak_achievements(
    streak_length: int, already_earned_codes: set[str]
) -> list[AchievementDef]:
    return [
        ach for threshold, ach in STREAK_ACHIEVEMENTS
        if streak_length >= threshold and ach.code not in already_earned_codes
    ]


def find_unlocked_count_achievements(
    habit_count: int, already_earned_codes: set[str]
) -> list[AchievementDef]:
    return [
        ach for threshold, ach in HABIT_COUNT_ACHIEVEMENTS
        if habit_count >= threshold and ach.code not in already_earned_codes
    ]
