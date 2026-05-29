"""Абстрактные интерфейсы внешних сервисов.

Они живут в application, а не в domain, потому что это всё-таки прикладные нужды.
Конкретные реализации (Anthropic, OpenAI, Whisper) — в infrastructure.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.application.dto.dtos import ExtractedHabitDTO


@runtime_checkable
class LLMCoach(Protocol):
    """Диалоговый коуч, поддерживает мульти-турновый контекст."""

    async def reply(
        self,
        user_message: str,
        history: list[dict],  # [{"role": "user"|"assistant", "content": "..."}]
        user_context: dict,   # streak'и, привычки, имя, стиль мотивации, memory
    ) -> str: ...


@runtime_checkable
class LLMSummarizer(Protocol):
    """Сжимает историю диалога в короткую memory summary (#7).

    На вход — старая summary + новые сообщения. На выход — обновлённая summary.
    Реализация — простой LLM-prompt: «обнови этот conspект».
    """

    async def summarize(
        self,
        previous_summary: str,
        new_messages: list[dict],  # [{"role": ..., "content": ...}]
    ) -> str: ...


@runtime_checkable
class LLMInsightFormatter(Protocol):
    """Превращает числовые факты в живой человеческий текст инсайта (#1).

    На вход — структурированные факты (dict с числами). На выход — короткий
    текст на 2-4 предложения. Если реализация недоступна — use case делает
    fallback в template-форматирование, поэтому интерфейс опциональный.
    """

    async def format_insight(self, facts: dict) -> str: ...


@runtime_checkable
class HabitExtractor(Protocol):
    """Извлечение структурированных привычек из произвольного текста.

    Реализуется через tool use / function calling.
    """

    async def extract(self, free_text: str) -> list[ExtractedHabitDTO]: ...


@runtime_checkable
class SpeechToText(Protocol):
    """Распознавание речи из голосового сообщения.

    На вход — путь к .ogg файлу (формат, в котором Telegram отдаёт голосовухи).
    На выход — расшифровка.
    """

    async def transcribe(self, audio_path: str) -> str: ...
