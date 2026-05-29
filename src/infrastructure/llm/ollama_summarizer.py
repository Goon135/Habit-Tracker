"""LLM-summarizer для long-term memory (#7).

Берёт предыдущую summary + пачку новых сообщений и просит LLM обновить summary.
Это «бедная» альтернатива векторному поиску: вместо retrieval мы держим короткий
плотный конспект, который всегда подкладываем в системный промпт коуча.

Формат summary — несколько коротких фактов:
- что мотивирует пользователя, что демотивирует;
- ключевые препятствия, паттерны;
- предпочтения по тону.
"""
from __future__ import annotations

import logging

from ollama import AsyncClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"
MAX_TOKENS = 400


_SUMMARIZE_PROMPT = """Ты — помощник, который ведёт краткий конспект ("memory") о пользователе трекера привычек, чтобы AI-коуч помнил его между сессиями.

Твоя задача: на основе предыдущего конспекта и новых сообщений из диалога — обновить конспект.

Правила:
- Конспект — на РУССКОМ языке.
- ОЧЕНЬ КРАТКО: 4-8 фактов в виде маркированного списка через дефис «-».
- Сохраняй устойчивые черты: что мотивирует пользователя, что демотивирует, ключевые препятствия, важные жизненные обстоятельства, предпочтения по тону общения.
- НЕ добавляй разовые мелочи (одно настроение в один день — не факт).
- НЕ цитируй сообщения дословно — формулируй обобщения.
- Удаляй устаревшие или противоречивые факты.
- Если новых значимых фактов нет — верни предыдущий конспект как есть.
- НИКОГДА не пиши приветствий, пояснений, мета-комментариев — только сам список фактов.

Формат ответа: только список через «-», без заголовков и пояснений."""


class OllamaSummarizer:
    def __init__(self, host: str = "http://localhost:11434", model: str = DEFAULT_MODEL) -> None:
        self._client = AsyncClient(host=host)
        self._model = model

    async def summarize(
        self,
        previous_summary: str,
        new_messages: list[dict],
    ) -> str:
        # Форматируем новые сообщения в простой диалог.
        dialog_lines = []
        for m in new_messages:
            role = "Пользователь" if m["role"] == "user" else "Коуч"
            dialog_lines.append(f"{role}: {m['content']}")
        dialog_block = "\n".join(dialog_lines) if dialog_lines else "(новых сообщений нет)"

        user_msg = (
            f"Предыдущий конспект:\n"
            f"{previous_summary or '(пусто)'}\n\n"
            f"Новые сообщения:\n{dialog_block}\n\n"
            f"Обновлённый конспект:"
        )

        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SUMMARIZE_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                options={
                    "temperature": 0.3,  # ниже temperature — фактологичнее.
                    "num_predict": MAX_TOKENS,
                },
            )
        except Exception as exc:
            logger.warning("Ollama summarize error: %r", exc)
            # Если суммаризатор сломался — возвращаем старую summary,
            # коуч продолжит работать без обновления.
            return previous_summary

        text = (response.message.content or "").strip()
        # Подстраховка: если LLM вернул бессмыслицу или пусто — оставляем старое.
        if not text or len(text) < 5:
            return previous_summary
        # Ограничиваем длину, чтобы summary не разрасталась бесконтрольно.
        if len(text) > 2000:
            text = text[:2000].rsplit("\n", 1)[0]
        return text
