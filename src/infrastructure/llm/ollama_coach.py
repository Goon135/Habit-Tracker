"""AI-коуч на базе локального Ollama (Llama 3.1 8B).

Архитектурно:
- Реализует Protocol LLMCoach из application слоя.
- Бот общается с Ollama через REST API на localhost:11434, никакой сети наружу.

С версии #1+#7 системный промпт собирается из четырёх частей:
1. Базовая инструкция (тон, безопасность).
2. Инструкция по стилю мотивации (#1) — из MotivationStyle.prompt_instruction.
3. Long-term memory summary (#7) — что коуч "помнит" о пользователе.
4. Текущий контекст: имя, привычки, streak'и, focus.
"""
from __future__ import annotations

import logging

from ollama import AsyncClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"
MAX_TOKENS = 512


_BASE_SYSTEM_PROMPT = """Ты — поддерживающий AI-коуч в трекере привычек. Твоя задача — помочь пользователю быть последовательным.

Базовые правила (важнее любого стиля):
- ВСЕГДА отвечаешь на русском языке.
- Краткий: 2-4 предложения, без длинных нумерованных списков.
- Никогда не критикуешь, не используешь стыд как мотиватор.
- Учитываешь данные о привычках пользователя, которые тебе дают.
- При признаках серьёзных проблем (депрессия, тревога, мысли о вреде себе)
  мягко предложи обратиться к специалисту.
- Не давай медицинских советов.

Если пользователь сообщает о срыве — нормализуй опыт, помоги извлечь урок.
Если хвастается успехом — порадуйся, отметь конкретное."""


class OllamaCoach:
    def __init__(self, host: str = "http://localhost:11434", model: str = DEFAULT_MODEL) -> None:
        self._client = AsyncClient(host=host)
        self._model = model

    async def reply(
        self,
        user_message: str,
        history: list[dict],
        user_context: dict,
    ) -> str:
        system = self._build_system(user_context)

        messages: list[dict] = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self._client.chat(
                model=self._model,
                messages=messages,
                options={
                    "temperature": 0.7,
                    "num_predict": MAX_TOKENS,
                },
            )
        except Exception as exc:
            logger.warning(
                "Ollama API error: type=%s repr=%r",
                type(exc).__name__,
                exc,
            )
            raise

        text = (response.message.content or "").strip()
        if not text:
            return "Извини, не могу ответить сейчас. Попробуй переформулировать?"
        return text

    @staticmethod
    def _build_system(context: dict) -> str:
        parts: list[str] = [_BASE_SYSTEM_PROMPT]

        # 1. Стиль мотивации (#1).
        motivation_instruction = context.get("motivation_instruction", "")
        if motivation_instruction:
            parts.append(f"\nСтиль общения с этим пользователем:\n{motivation_instruction}")

        # 2. Long-term memory (#7).
        memory = context.get("memory_summary", "").strip()
        if memory:
            parts.append(
                "\nЧто ты уже знаешь о пользователе из предыдущих разговоров "
                "(используй это, но не цитируй напрямую):\n" + memory
            )

        # 3. Контекст: имя, фокус, привычки.
        name = context.get("first_name") or "пользователь"
        focus = context.get("priority_focus_label", "")

        habits = context.get("habits") or []
        habit_lines = []
        for h in habits:
            line = (
                f"- {h['name']} ({h['category']}): серия {h['streak']} дн., "
                f"за последние 7 дней — {h['last_7_days_completed']}/7"
            )
            # Количественные привычки и цели — добавляем доп. инфо.
            if h.get("target_value"):
                line += f", цель: {h['target_value']} {h.get('unit') or ''}"
            if h.get("is_goal") and h.get("end_date"):
                line += f", дедлайн: {h['end_date']}"
            habit_lines.append(line)
        habits_block = "\n".join(habit_lines) if habit_lines else "(пока нет привычек)"

        ctx_block = f"\n\nИмя пользователя: {name}."
        if focus:
            ctx_block += f"\nЧто ему важнее: {focus}."
        ctx_block += f"\nТекущие привычки:\n{habits_block}"

        parts.append(ctx_block)
        return "".join(parts)
