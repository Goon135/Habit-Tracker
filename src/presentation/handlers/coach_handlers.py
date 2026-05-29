"""AI-коуч + извлечение привычек из произвольного текста.

Поведение для входящего текстового сообщения, которое не попадает ни под кнопку,
ни под FSM:
- Если пользователь сейчас в режиме «AI-коуч» (CoachChat state) — отправляем в коуч.
- Иначе пробуем извлечь привычки: если извлеклись — создаём, отчитываемся.
- Если не извлеклись и пользователь в LLM-группе — всё-таки отвечаем как коуч.
- Если шаблонная группа — даём подсказку.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.application.use_cases.coach_reply import CoachReplyUseCase
from src.application.use_cases.extract_habits import ExtractHabitsFromTextUseCase
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.coaching_mode import CoachingMode
from src.presentation.handlers.states import CoachChat


def build_router(
    coach_reply: CoachReplyUseCase,
    extract_habits: ExtractHabitsFromTextUseCase,
    users: UserRepository,
) -> Router:
    router = Router(name="coach")

    @router.message(F.text == "💬 AI-коуч")
    @router.message(Command("coach"))
    async def enter_coach(message: Message, state: FSMContext) -> None:
        user = await users.get(message.from_user.id)
        if user is None:
            await message.answer("Сначала /start.")
            return

        await state.set_state(CoachChat.chatting)
        if user.coaching_mode == CoachingMode.LLM:
            await message.answer(
                "💬 Я слушаю. Расскажи, как идут дела, что не получается, что радует.\n"
                "Чтобы выйти из режима коуча — отправь /stop."
            )
        else:
            await message.answer(
                "💬 Поддержка включена. Расскажи, как дела — я отвечу подсказкой.\n"
                "Чтобы выйти — отправь /stop."
            )

    @router.message(CoachChat.chatting, Command("stop"))
    async def exit_coach(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Вышли из режима коуча. Возвращайся, когда захочешь.")

    @router.message(CoachChat.chatting, F.text)
    async def coach_dialog(message: Message) -> None:
        reply = await coach_reply.execute(message.from_user.id, message.text)
        await message.answer(reply.text)

    # Произвольный текст вне состояний и кнопок: пробуем извлечь привычки,
    # а если не вышло — отвечаем коучем (или дефолтной подсказкой).
    @router.message(F.text & ~F.text.startswith("/"))
    async def free_text_fallback(message: Message) -> None:
        text = message.text.strip()
        # Игнорируем кнопочные надписи — у них свои хэндлеры выше по приоритету.
        # Сюда долетит только то, что не совпало ни с чем.

        # 1. Пробуем извлечь привычки.
        import logging
        log = logging.getLogger("habitbot.handlers.coach")
        log.info("free_text_fallback: raw_text=%r", text)
        try:
            created = await extract_habits.execute(message.from_user.id, text)
            log.info("free_text_fallback: created %d habits: %r",
                     len(created), [(h.id, h.name) for h in created])
        except Exception as exc:
            log.exception("free_text_fallback: extract failed: %s", exc)
            created = []

        if created:
            lines = ["✅ Я понял, что ты хочешь начать:\n"]
            for h in created:
                lines.append(f"  • {h.name} ({h.category.value}, {h.frequency.kind})")
            lines.append("\nПривычки уже добавлены. Можешь начать отмечать их выполнение.")
            await message.answer("\n".join(lines))
            return

        # 2. Иначе отвечаем коучем — это допустимо для любой группы, разница только
        # в том, чем ответит use case внутри.
        reply = await coach_reply.execute(message.from_user.id, text)
        await message.answer(reply.text)

    return router
