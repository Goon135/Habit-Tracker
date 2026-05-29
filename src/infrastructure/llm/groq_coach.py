"""AI-коуч на базе Groq API (Llama 3.3 70B).

Архитектурно:
- Реализует Protocol LLMCoach из application слоя.
- Groq API OpenAI-совместимый, но мы используем нативный SDK `groq` —
  он чуть удобнее (асинхронный клиент, явные типы).

Особенности бесплатного tier'а Groq (актуально на 2026):
- llama-3.3-70b-versatile: 30 RPM, 1000 RPD, 6000 TPM. Это в 3 раза больше RPM,
  чем у Gemini Free, чего для дипломного бота с большим запасом.
- Без географических ограничений (в отличие от Gemini).
- Не требует карты, ключ получается на console.groq.com за 2 минуты.
- Очень быстрый: LPU-чипы Groq дают ~800 токенов/сек, ответы прилетают за
  доли секунды. Это даёт хороший UX в боте.

Качество русского у Llama 3.3 70B хорошее: модель Meta обучена на многоязычном
корпусе, для коучинговых реплик подходит. Чуть ниже, чем Gemini 2.5 Flash, но
разницы пользователь не заметит.
"""
from __future__ import annotations

import logging

from groq import AsyncGroq

logger = logging.getLogger(__name__)

# llama-3.3-70b-versatile: 30 RPM / 1000 RPD на бесплатном tier'е.
MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 512


_SYSTEM_PROMPT = """Ты — поддерживающий AI-коуч в трекере привычек. Твоя задача — помочь пользователю быть последовательным.

Стиль общения:
- Тёплый, эмпатичный, без морализаторства и нравоучений.
- Краткий: 2-4 предложения, без длинных нумерованных списков.
- Спрашиваешь уточняющие вопросы, если ситуация требует понимания контекста.
- Никогда не критикуешь, не используешь стыд как мотиватор.
- Учитываешь данные о привычках пользователя, которые тебе дают.
- ВСЕГДА отвечаешь на русском языке.

Если пользователь сообщает о срыве или пропуске — нормализуй опыт, помоги извлечь урок,
без советов вроде "просто соберись".

Если пользователь хвастается успехом — искренне порадуйся, отметь конкретное.

Не давай медицинских советов. При признаках серьёзных проблем (депрессия, тревога)
мягко предложи обратиться к специалисту."""


class GroqCoach:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncGroq(api_key=api_key)

    async def reply(
        self,
        user_message: str,
        history: list[dict],
        user_context: dict,
    ) -> str:
        system = self._build_system(user_context)

        # OpenAI-совместимый формат: [{role: "system"|"user"|"assistant", content: str}]
        messages: list[dict] = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self._client.chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=MAX_TOKENS,
                temperature=0.7,
            )
        except Exception as exc:
            # GroqError при rate limit / 429 — поднимаем наверх, GracefulCoach обработает.
            logger.warning("Groq API error: %s", exc)
            raise

        text = (response.choices[0].message.content or "").strip()
        if not text:
            return "Извини, не могу ответить сейчас. Попробуй переформулировать?"
        return text

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
