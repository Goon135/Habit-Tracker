"""Категория привычки. Value object: иммутабельный, сравнивается по значению."""
from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    HEALTH = "Здоровье"
    LEARNING = "Обучение"
    SPORT = "Спорт"
    MINDFULNESS = "Осознанность"
    WORK = "Работа"
    CREATIVITY = "Творчество"
    GENERAL = "Общее"

    @classmethod
    def from_string(cls, raw: str) -> "Category":
        """Принимает русское или английское имя, возвращает enum.

        Используется при разборе LLM-ответа: модель может вернуть как русское
        значение, так и английский ключ — нужна устойчивость.
        """
        if not raw:
            return cls.GENERAL
        raw_clean = raw.strip()
        for member in cls:
            if member.value == raw_clean or member.name.lower() == raw_clean.lower():
                return member
        return cls.GENERAL
