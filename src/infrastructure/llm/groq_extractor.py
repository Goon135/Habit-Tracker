"""Извлечение привычек через Groq function calling.

Используем меньшую модель — llama-3.1-8b-instant: structured extraction задача
не требует мощи 70B, а 8B даёт 30 RPM с большим запасом и работает в 2-3 раза
быстрее. Function calling у Llama 3.1 8B стабильный для простых схем.

Принцип идентичен Anthropic tool use / Gemini function calling, но через
OpenAI-совместимый формат tools: модель возвращает tool_calls в response,
мы парсим аргументы из JSON.
"""
from __future__ import annotations

import json
import logging

from groq import AsyncGroq

from src.application.dto.dtos import ExtractedHabitDTO

logger = logging.getLogger(__name__)

MODEL = "llama-3.1-8b-instant"


_TOOL = {
    "type": "function",
    "function": {
        "name": "save_habits",
        "description": (
            "Сохранить список привычек, извлечённых из сообщения пользователя. "
            "Если пользователь упомянул несколько привычек — верни их все. "
            "Если описал одну — верни список из одного элемента. "
            "Если в тексте нет привычек — верни habits=[]."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "habits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": (
                                    "Короткое название привычки, как пользователь "
                                    "увидит её в списке. Например: 'Бегать по утрам', "
                                    "'Читать перед сном'."
                                ),
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "Здоровье", "Обучение", "Спорт",
                                    "Осознанность", "Работа", "Творчество", "Общее",
                                ],
                                "description": "Категория привычки.",
                            },
                            "frequency_kind": {
                                "type": "string",
                                "enum": ["daily", "weekly_n", "weekdays"],
                                "description": (
                                    "Тип расписания. 'daily' — каждый день. "
                                    "'weekly_n' — N раз в неделю без фиксации дней. "
                                    "'weekdays' — конкретные дни недели."
                                ),
                            },
                            "times_per_week": {
                                "type": "integer",
                                "description": (
                                    "Для frequency_kind='weekly_n', сколько раз "
                                    "в неделю (1-7)."
                                ),
                            },
                            "weekdays": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": (
                                    "Для frequency_kind='weekdays': "
                                    "0=Пн, 1=Вт, ..., 6=Вс."
                                ),
                            },
                        },
                        "required": ["name", "category", "frequency_kind"],
                    },
                },
            },
            "required": ["habits"],
        },
    },
}


_SYSTEM = (
    "Ты — парсер привычек. Получаешь произвольный текст и извлекаешь из него привычки. "
    "Всегда отвечай вызовом инструмента save_habits, не пиши обычный текст."
)


class GroqHabitExtractor:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncGroq(api_key=api_key)

    async def extract(self, free_text: str) -> list[ExtractedHabitDTO]:
        if not free_text.strip():
            return []

        try:
            response = await self._client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": free_text},
                ],
                tools=[_TOOL],
                # tool_choice="required" — форсирует вызов какого-то инструмента (у нас он один).
                tool_choice="required",
                temperature=0.0,  # детерминизм при извлечении
            )
        except Exception as exc:
            logger.warning("Groq extraction error: %s", exc)
            return []

        message = response.choices[0].message
        if not message.tool_calls:
            return []

        for tool_call in message.tool_calls:
            if tool_call.function.name != "save_habits":
                continue
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                logger.warning(
                    "Failed to parse tool_call arguments: %s",
                    tool_call.function.arguments[:200],
                )
                continue
            raw_habits = args.get("habits", []) or []
            return [self._to_dto(h) for h in raw_habits]
        return []

    @staticmethod
    def _to_dto(raw: dict) -> ExtractedHabitDTO:
        return ExtractedHabitDTO(
            name=str(raw.get("name", "")).strip(),
            category=str(raw.get("category", "Общее")),
            frequency_kind=str(raw.get("frequency_kind", "daily")),
            times_per_week=raw.get("times_per_week"),
            weekdays=list(raw.get("weekdays") or []),
        )
