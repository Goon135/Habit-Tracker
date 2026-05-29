"""Use case: ответ AI-коуча.

КЛЮЧЕВАЯ ЛОГИКА ДЛЯ ИССЛЕДОВАТЕЛЬСКОЙ ЧАСТИ ДИПЛОМА.

В зависимости от A/B-группы пользователя:
- TEMPLATE: возвращаем заранее заготовленный шаблон по простой эвристике.
- LLM: вызываем LLMCoach с историей диалога и контекстом пользователя.

Также:
- Используем motivation_style и priority_focus для персонализации (#1).
- Используем memory_summary как long-term memory (#7).
- Раз в N новых сообщений обновляем memory_summary.

Оба пути логируют ответ в БД через CoachMessageRepository — это даёт
данные для последующего анализа retention/engagement.
"""
from __future__ import annotations

import logging
import random
from datetime import date, timedelta

from src.application.dto.dtos import CoachReplyDTO
from src.application.interfaces.ai_services import LLMCoach, LLMSummarizer
from src.domain.entities.coach_message import CoachMessage, CoachRole
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import CoachMessageRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.coaching_mode import CoachingMode
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.streak import Streak

logger = logging.getLogger(__name__)

# Каждые N новых пар (user+assistant) пересобираем memory_summary.
# 6 пар ≈ полтора-два диалога — частота нормальная, не зальёт LLM.
MEMORY_REFRESH_EVERY_N_MESSAGES = 12  # это пар × 2 ролей.


_TEMPLATES_RELAPSE = [
    "Не страшно, срывы — часть процесса. Главное — не сдаться завтра.",
    "Один пропуск не ломает всё. Возвращайся к привычке как можно скорее.",
    "Что мешало сегодня? Подумай, что можно сделать иначе.",
]
_TEMPLATES_PROGRESS = [
    "Ты на верном пути! Продолжай.",
    "Серия растёт — это значит, привычка укрепляется.",
    "Отличная работа. Не сбавляй темп.",
]
_TEMPLATES_DEFAULT = [
    "Расскажи подробнее, я слушаю.",
    "Понимаю. Что ты сам думаешь об этом?",
    "Это важно. Что тебе сейчас помогло бы?",
]


class CoachReplyUseCase:
    def __init__(
        self,
        users: UserRepository,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        coach_messages: CoachMessageRepository,
        llm_coach: LLMCoach,
        summarizer: LLMSummarizer | None = None,
    ) -> None:
        self._users = users
        self._habits = habits
        self._logs = habit_logs
        self._messages = coach_messages
        self._llm = llm_coach
        self._summarizer = summarizer

    async def execute(self, user_id: int, user_message: str) -> CoachReplyDTO:
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")

        # Логируем входящее сообщение в обоих режимах — иначе нечего сравнивать.
        await self._messages.add(
            CoachMessage(user_id=user_id, role=CoachRole.USER, content=user_message)
        )

        if user.coaching_mode == CoachingMode.TEMPLATE:
            reply_text = self._template_reply(user_message)
        else:
            reply_text = await self._llm_reply(user, user_message)

        await self._messages.add(
            CoachMessage(user_id=user_id, role=CoachRole.ASSISTANT, content=reply_text)
        )

        # После ответа: проверяем, не пора ли пересчитать memory summary (#7).
        # Делаем только в LLM-режиме — в template-группе memory не нужна.
        if user.coaching_mode == CoachingMode.LLM and self._summarizer is not None:
            try:
                await self._maybe_refresh_memory(user_id)
            except Exception as exc:
                logger.warning("memory refresh failed: %r", exc)

        return CoachReplyDTO(text=reply_text, mode=user.coaching_mode.value)

    def _template_reply(self, user_message: str) -> str:
        """Контрольная группа: примитивная эвристика по ключевым словам."""
        text = user_message.lower()
        relapse_words = ("сорвал", "не смог", "пропусти", "забыл", "лень", "устал")
        progress_words = ("сделал", "получилось", "выполнил", "молодец", "удалось")

        if any(w in text for w in relapse_words):
            pool = _TEMPLATES_RELAPSE
        elif any(w in text for w in progress_words):
            pool = _TEMPLATES_PROGRESS
        else:
            pool = _TEMPLATES_DEFAULT
        return random.choice(pool)

    async def _llm_reply(self, user, user_message: str) -> str:
        """Экспериментальная группа: LLM с историей, контекстом, memory и стилем."""
        history_entities = await self._messages.list_recent(user.id, limit=20)
        history = [
            {"role": m.role.value, "content": m.content}
            for m in history_entities
            if m.content != user_message
        ]

        context = await self._build_user_context(user, user.first_name)
        return await self._llm.reply(
            user_message=user_message,
            history=history,
            user_context=context,
        )

    async def _build_user_context(self, user, first_name: str) -> dict:
        habits = await self._habits.list_for_user(user.id, active_only=True)
        today = date.today()
        habit_summary = []
        for h in habits:
            completed_dates = await self._logs.list_completed_dates(h.id)
            streak = Streak.calculate(completed_dates, today)
            week_ago = today - timedelta(days=6)
            recent_count = sum(1 for d in completed_dates if d >= week_ago)
            habit_summary.append({
                "name": h.name,
                "category": h.category.value,
                "streak": streak.length,
                "last_7_days_completed": recent_count,
                "target_value": h.target_value,
                "unit": h.unit,
                "is_goal": h.is_goal,
                "end_date": h.end_date.isoformat() if h.end_date else None,
            })

        # Стиль мотивации и фокус — для системного промпта.
        # В recovery mode принудительно переключаем на GENTLE,
        # независимо от выбранного стиля (#3).
        style = user.motivation_style
        if user.is_in_recovery():
            style = MotivationStyle.GENTLE
        motivation_instruction = ""
        if style != MotivationStyle.NOT_SET:
            motivation_instruction = style.prompt_instruction

        focus_label = ""
        if user.priority_focus.value != "not_set":
            focus_label = user.priority_focus.label

        return {
            "first_name": first_name,
            "habits": habit_summary,
            "motivation_instruction": motivation_instruction,
            "priority_focus_label": focus_label,
            "memory_summary": user.memory_summary or "",
        }

    async def _maybe_refresh_memory(self, user_id: int) -> None:
        """Раз в N сообщений просим summarizer обновить memory_summary."""
        # Достаём последние N сообщений; если их меньше N — рано.
        recent = await self._messages.list_recent(user_id, limit=MEMORY_REFRESH_EVERY_N_MESSAGES)
        if len(recent) < MEMORY_REFRESH_EVERY_N_MESSAGES:
            return

        user = await self._users.get(user_id)
        if user is None:
            return

        # Простая эвристика «не чаще раза в N сообщений»: если memory_updated_at
        # обновлялась после последнего сообщения из этой пачки — рано.
        # Это покрывает кейс «юзер общается медленно, мы не дёргаем summarizer каждый раз».
        if user.memory_updated_at is not None:
            last_msg_time = recent[-1].created_at
            if user.memory_updated_at >= last_msg_time:
                return

        new_msgs = [{"role": m.role.value, "content": m.content} for m in recent]
        new_summary = await self._summarizer.summarize(user.memory_summary, new_msgs)
        if new_summary and new_summary != user.memory_summary:
            user.update_memory_summary(new_summary)
            await self._users.save(user)
            logger.info("memory refreshed for user %s (len=%d)", user_id, len(new_summary))
