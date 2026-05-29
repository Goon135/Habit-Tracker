"""Извлечение привычек из произвольного текста через Gemini function calling.

Используем gemini-2.5-flash-lite на extraction — у него выше RPD (1000) и он дешевле
по compute, а задача структурного извлечения не требует мощной модели.

Принцип: декларируем функцию save_habits, форсируем её вызов через
tool_config={"function_calling_config": {"mode": "ANY"}}. Эквивалент Anthropic
tool_choice={type:"tool", name:...}.
"""
from __future__ import annotations

import logging

from google import genai
from google.genai import types

from src.application.dto.dtos import ExtractedHabitDTO

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash-lite"  # бесплатный tier: 15 RPM, 1000 RPD


# Декларируем схему функции по образцу OpenAI/JSON Schema — Gemini её понимает.
_SAVE_HABITS_DECLARATION = {
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
                                "Короткое название привычки, как пользователь бы её увидел "
                                "в списке. Например: 'Бегать по утрам', 'Читать перед сном'."
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
                            "description": "Для frequency_kind='weekly_n', сколько раз в неделю (1-7).",
                        },
                        "weekdays": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Для frequency_kind='weekdays': 0=Пн, …, 6=Вс.",
                        },
                    },
                    "required": ["name", "category", "frequency_kind"],
                },
            },
        },
        "required": ["habits"],
    },
}


_SYSTEM = (
    "Ты — парсер привычек. Получаешь произвольный текст и извлекаешь из него привычки. "
    "Всегда отвечай вызовом инструмента save_habits, не пиши обычный текст."
)


class GeminiHabitExtractor:
    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    async def extract(self, free_text: str) -> list[ExtractedHabitDTO]:
        if not free_text.strip():
            return []

        tools = [types.Tool(function_declarations=[_SAVE_HABITS_DECLARATION])]

        # mode="ANY" — форсирует, что модель ОБЯЗАНА вызвать tool, а не отвечать текстом.
        # allowed_function_names ограничивает выбор конкретной функцией.
        tool_config = types.ToolConfig(
            function_calling_config=types.FunctionCallingConfig(
                mode="ANY",
                allowed_function_names=["save_habits"],
            )
        )

        config = types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            tools=tools,
            tool_config=tool_config,
            temperature=0.0,  # детерминизм при извлечении
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=free_text,
                config=config,
            )
        except Exception as exc:
            logger.warning("Gemini extraction error: %s", exc)
            return []

        # Достаём function call из ответа. Структура:
        # response.candidates[0].content.parts[i].function_call
        for candidate in (response.candidates or []):
            for part in (candidate.content.parts or []):
                fc = getattr(part, "function_call", None)
                if fc is not None and fc.name == "save_habits":
                    raw_args = dict(fc.args or {})
                    raw_habits = raw_args.get("habits", []) or []
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
