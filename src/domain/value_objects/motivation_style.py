"""Стиль мотивации пользователя — как AI-коуч должен с ним общаться.

Заполняется через онбординг-опрос после /start. В отличие от CoachingMode
(A/B-эксперимент), это пользовательская настройка, которую он может менять
в /settings.

NOT_SET — отдельное состояние: пользователь ещё не прошёл онбординг.
"""
from __future__ import annotations

from enum import Enum


class MotivationStyle(str, Enum):
    NOT_SET = "not_set"            # ещё не выбрал
    SUPPORTIVE = "supportive"      # мягкая поддержка, эмпатия
    DISCIPLINE = "discipline"      # жёсткий контроль, прямота
    COMPETITION = "competition"    # сравнение с прошлым, очки, серии
    GENTLE = "gentle"              # минимум давления, recovery-friendly
    PRODUCTIVITY = "productivity"  # фокус на результате, метриках

    @property
    def label(self) -> str:
        return _LABELS.get(self, "Не задан")

    @property
    def description(self) -> str:
        return _DESCRIPTIONS.get(self, "")

    @property
    def prompt_instruction(self) -> str:
        """Инструкция, которая добавляется в системный промпт LLM."""
        return _PROMPT_INSTRUCTIONS.get(self, "")


_LABELS = {
    MotivationStyle.SUPPORTIVE: "🤗 Поддержка",
    MotivationStyle.DISCIPLINE: "🎯 Дисциплина",
    MotivationStyle.COMPETITION: "🏆 Соревнование",
    MotivationStyle.GENTLE: "🌿 Мягкий режим",
    MotivationStyle.PRODUCTIVITY: "⚡ Продуктивность",
}

_DESCRIPTIONS = {
    MotivationStyle.SUPPORTIVE: "Тёплый тон, эмпатия, помощь в сложные моменты",
    MotivationStyle.DISCIPLINE: "Прямые формулировки, чёткие напоминания, без поблажек",
    MotivationStyle.COMPETITION: "Очки, серии, рекорды — сравнение с собой прошлым",
    MotivationStyle.GENTLE: "Минимум давления, recovery-mode при срывах",
    MotivationStyle.PRODUCTIVITY: "Метрики, результаты, эффективность",
}

_PROMPT_INSTRUCTIONS = {
    MotivationStyle.SUPPORTIVE: (
        "Стиль ответов: тёплый, эмпатичный, поддерживающий. Нормализуй сложности, "
        "не торопи. При срывах — сочувствуй и помогай найти причину без осуждения. "
        "Используй мягкие формулировки: «попробуй», «может быть», «ничего страшного»."
    ),
    MotivationStyle.DISCIPLINE: (
        "Стиль ответов: прямой, без сантиментов. Конкретные шаги, чёткие напоминания. "
        "Не размазывай эмпатию — пользователь хочет дисциплины. "
        "Используй формулировки: «сделай», «не откладывай», «вот план»."
    ),
    MotivationStyle.COMPETITION: (
        "Стиль ответов: упор на достижения и сравнение с прошлым. "
        "Подчёркивай серии, очки, рекорды. Бросай вызов: «можешь ли превзойти прошлую неделю?». "
        "Используй формулировки: «твой рекорд», «новый максимум», «обходишь себя прошлого»."
    ),
    MotivationStyle.GENTLE: (
        "Стиль ответов: максимально мягкий, без давления. При спаде — предлагай "
        "упрощать, отдыхать, делать меньше. Не настаивай. Не используй слова "
        "«должен», «нужно». Используй: «как насчёт», «если захочется», «можно и так»."
    ),
    MotivationStyle.PRODUCTIVITY: (
        "Стиль ответов: фокус на результате и метриках. Цифры, проценты, эффективность. "
        "Минимум small talk. Используй формулировки: «выполнение X%», "
        "«оптимально», «KPI», «прогресс по неделе»."
    ),
}
