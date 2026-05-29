"""LLM-форматтер инсайтов (#1).

На вход — словарь с уже посчитанными фактами (числа, проценты, дни).
На выход — короткий человечный текст на русском.

LLM здесь НЕ считает и НЕ интерпретирует — только переводит цифры в язык.
Это критично: правила объяснимы и проверяемы, LLM только косметика.

Если LLM возвращает что-то странное — use case делает fallback на
template-форматирование, сохраняя цифры.
"""
from __future__ import annotations

import logging

from ollama import AsyncClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"
MAX_TOKENS = 300


_SYSTEM_PROMPT = """Ты — аналитик трекера привычек. Тебе дают набор УЖЕ ПОСЧИТАННЫХ фактов о пользователе. Твоя задача — переформулировать их в короткий живой текст.

Жёсткие правила:
- Текст НА РУССКОМ.
- 2-4 предложения, не больше.
- НЕ ВЫДУМЫВАЙ цифр и фактов, которых нет во входных данных. Если факта нет — не упоминай.
- Используй конкретные числа из фактов (проценты, дни недели, количество).
- Без воды и пустых ободрений типа «продолжай в том же духе».
- Если есть рекомендация — она должна логически вытекать из фактов.
- НИКОГДА не начинай со слов «Привет», «Окей», «Понятно».
- Не используй markdown-разметку.

Формат ответа: только сам текст инсайта, без префиксов, кавычек или пояснений."""


class OllamaInsightFormatter:
    def __init__(self, host: str = "http://localhost:11434", model: str = DEFAULT_MODEL) -> None:
        self._client = AsyncClient(host=host)
        self._model = model

    async def format_insight(self, facts: dict) -> str:
        # Формируем компактный буллет-лист фактов.
        bullets = []
        for k, v in facts.items():
            if v is None or v == "" or v == []:
                continue
            bullets.append(f"- {k}: {v}")
        facts_block = "\n".join(bullets) if bullets else "(нет значимых фактов)"

        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Факты:\n{facts_block}\n\n"
                            "Сформулируй краткий персональный инсайт:"
                        ),
                    },
                ],
                options={"temperature": 0.5, "num_predict": MAX_TOKENS},
            )
        except Exception as exc:
            logger.warning("Ollama insight formatter error: %r", exc)
            return ""

        text = (response.message.content or "").strip()
        # Защита от слишком длинных или пустых ответов.
        if not text or len(text) < 10:
            return ""
        if len(text) > 1200:
            text = text[:1200].rsplit(".", 1)[0] + "."
        return text
