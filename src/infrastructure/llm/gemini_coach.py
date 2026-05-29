"""AI-коуч на базе Google Gemini (бесплатный tier).

Архитектурно важно:
- Реализует Protocol LLMCoach из application слоя.
- Не знает о репозиториях БД — контекст приходит готовый из use case.

Особенности бесплатного tier'а Gemini (актуально на 2026):
- gemini-2.5-flash: 10 RPM, 250 RPD, 250К TPM. Используем для коуча — для диалога
  нужна модель повыше качеством, чем flash-lite, а 250 запросов в день более чем
  достаточно для дипломного бота.
- Бесплатные запросы могут использоваться Google для улучшения моделей. PII в
  системном промпте не отправляем (только first_name и нумерация привычек).

Если уперлись в RPD — конверсия пользователя с коучем в этот день не работает,
бот возвращает извинение. Это поведение мы тестируем явно (см. тесты).
"""
from __future__ import annotations

import asyncio
import logging

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# gemini-2.5-flash на бесплатном tier'е: 10 RPM, 250 RPD, 250К TPM
MODEL = "gemini-2.5-flash"
MAX_OUTPUT_TOKENS = 512


_SYSTEM_PROMPT = """Ты — поддерживающий AI-коуч в трекере привычек. Твоя задача — помочь пользователю быть последовательным.

Стиль общения:
- Тёплый, эмпатичный, без морализаторства и нравоучений.
- Краткий: 2-4 предложения, без длинных нумерованных списков.
- Спрашиваешь уточняющие вопросы, если ситуация требует понимания контекста.
- Никогда не критикуешь, не используешь стыд как мотиватор.
- Учитываешь данные о привычках пользователя, которые тебе дают.

Если пользователь сообщает о срыве или пропуске — нормализуй опыт, помоги извлечь урок,
без советов вроде "просто соберись".

Если пользователь хвастается успехом — искренне порадуйся, отметь конкретное.

Не давай медицинских советов. При признаках серьёзных проблем (депрессия, тревога)
мягко предложи обратиться к специалисту."""


class GeminiCoach:
    def __init__(self, api_key: str) -> None:
        # google-genai SDK сам определяет sync/async режим по способу вызова.
        # Используем aio.* для асинхронного API.
        self._client = genai.Client(api_key=api_key)

    async def reply(
        self,
        user_message: str,
        history: list[dict],
        user_context: dict,
    ) -> str:
        # Gemini принимает историю в формате [{role, parts: [{text}]}]
        # с role: "user" | "model" (в отличие от OpenAI/Anthropic, где "assistant").
        contents = self._build_contents(history, user_message)
        system_instruction = self._build_system(user_context)

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.7,
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL,
                contents=contents,
                config=config,
            )
        except Exception as exc:
            # Самая частая ошибка — 429 RESOURCE_EXHAUSTED (превышен RPM или RPD).
            # Поднимаем наверх — use case обработает.
            logger.warning("Gemini API error: %s", exc)
            raise

        text = (response.text or "").strip()
        if not text:
            # Защита: иногда модель возвращает пустой ответ при срабатывании фильтров.
            return "Извини, не могу ответить сейчас. Попробуй переформулировать?"
        return text

    @staticmethod
    def _build_contents(history: list[dict], user_message: str) -> list[dict]:
        """Конвертирует {role, content} → Gemini {role, parts: [{text}]}.

        role mapping:
            "user" → "user"
            "assistant" → "model"
        """
        contents = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})
        contents.append({"role": "user", "parts": [{"text": user_message}]})
        return contents

    @staticmethod
    def _build_system(context: dict) -> str:
        name = context.get("first_name") or "пользователь"
        habits = context.get("habits") or []
        habit_lines = []
        for h in habits:
            habit_lines.append(
                f"- {h['name']} ({h['category']}): серия {h['streak']} дн., "
                f"за последние 7 дней — {h['last_7_days_completed']}/7"
            )
        habits_block = "\n".join(habit_lines) if habit_lines else "(пока нет привычек)"
        return (
            _SYSTEM_PROMPT
            + f"\n\nПользователя зовут: {name}.\n"
            + f"Текущие привычки пользователя:\n{habits_block}"
        )
