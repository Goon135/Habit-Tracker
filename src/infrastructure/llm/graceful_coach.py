"""Обёртка над LLMCoach с graceful degradation при rate limit.

Зачем нужна: бесплатный tier любого LLM-провайдера (Groq, Gemini, OpenAI) имеет
лимиты — RPM (запросов в минуту) и RPD (в день). При уперевшемся лимите вместо
traceback мы хотим вернуть осмысленный fallback, чтобы UX не ломался и демо к
диплому прошло без сюрпризов.

Опционально: при систематических 429 в течение последних N минут вырубаем LLM-режим
на cooldown_seconds и переходим на template-логику. Это защитный механизм для
демонстраций — если внезапно кончились лимиты, бот всё равно продолжит отвечать
(просто шаблонами).
"""
from __future__ import annotations

import logging
import time

from src.application.interfaces.ai_services import LLMCoach

logger = logging.getLogger(__name__)


_RATE_LIMIT_FALLBACK = (
    "Извини, я сегодня уже много общался и временно отдыхаю. "
    "Расскажи мне о своих привычках чуть позже — через несколько минут или завтра. "
    "А пока попробуй просто отметить выполнение или создать новую привычку."
)


class GracefulCoach:
    """Оборачивает любой LLMCoach. При 429/RESOURCE_EXHAUSTED возвращает fallback."""

    def __init__(
        self,
        inner: LLMCoach,
        cooldown_seconds: int = 60,
    ) -> None:
        self._inner = inner
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float = 0.0

    async def reply(
        self,
        user_message: str,
        history: list[dict],
        user_context: dict,
    ) -> str:
        now = time.monotonic()
        if now < self._cooldown_until:
            return _RATE_LIMIT_FALLBACK

        try:
            return await self._inner.reply(user_message, history, user_context)
        except Exception as exc:
            # Распознаём rate limit по строке ошибки — у google.genai нет общего класса
            # для всех 429. Это устойчивее, чем except по конкретному типу.
            msg = str(exc).lower()
            is_rate_limit = any(s in msg for s in (
                "429", "resource_exhausted", "rate limit", "quota",
            ))
            if is_rate_limit:
                logger.warning("Rate limit hit, entering cooldown for %ds", self._cooldown_seconds)
                self._cooldown_until = now + self._cooldown_seconds
                return _RATE_LIMIT_FALLBACK
            # Другие ошибки (5xx, сетевые) — поднимаем дальше, пусть use case логирует.
            raise
