"""Хэндлеры онбординга (#1).

После /start, если пользователь ещё не прошёл онбординг, бот задаёт ему
2 вопроса: стиль мотивации и фокус (серия vs прогресс). Результат сохраняется
в User и потом используется AI-коучем для адаптации стиля.

Онбординг можно пройти повторно командой /onboarding или из настроек
(только смена стиля).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.application.use_cases.onboarding import (
    CompleteOnboardingUseCase,
    UpdateMotivationStyleUseCase,
)
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus
from src.presentation.handlers.states import Onboarding
from src.presentation.keyboards.keyboards import focus_kb, main_menu, motivation_kb


def build_router(
    complete_onboarding: CompleteOnboardingUseCase,
    update_motivation: UpdateMotivationStyleUseCase,
    users: UserRepository,
) -> Router:
    router = Router(name="onboarding")

    # ────────  Запуск опроса ────────

    async def start_questionnaire(message: Message, state: FSMContext) -> None:
        await state.set_state(Onboarding.waiting_motivation)
        await message.answer(
            "Прежде чем начнём — два коротких вопроса, чтобы я подстроился под тебя.\n\n"
            "1️⃣ Что тебя лучше мотивирует?",
            reply_markup=motivation_kb(prefix="onb_mot"),
        )

    @router.message(Command("onboarding"))
    async def cmd_onboarding(message: Message, state: FSMContext) -> None:
        await start_questionnaire(message, state)

    # Внешний хук, чтобы /start мог запустить опрос, не зная его внутренней реализации.
    router.start_questionnaire = start_questionnaire  # type: ignore[attr-defined]

    # ────────  Шаги опроса ────────

    @router.callback_query(Onboarding.waiting_motivation, F.data.startswith("onb_mot:"))
    async def on_motivation(callback: CallbackQuery, state: FSMContext) -> None:
        raw = callback.data.split(":", 1)[1]
        try:
            style = MotivationStyle(raw)
        except ValueError:
            await callback.answer("Неизвестный стиль", show_alert=True)
            return
        await state.update_data(motivation=style.value)
        await state.set_state(Onboarding.waiting_focus)
        await callback.message.edit_text(
            f"Выбрано: {style.label}\n_{style.description}_\n\n"
            "2️⃣ Что для тебя важнее в трекере привычек?",
            reply_markup=focus_kb(),
            parse_mode="Markdown",
        )
        await callback.answer()

    @router.callback_query(Onboarding.waiting_focus, F.data.startswith("onb_focus:"))
    async def on_focus(callback: CallbackQuery, state: FSMContext) -> None:
        raw = callback.data.split(":", 1)[1]
        try:
            focus = PriorityFocus(raw)
        except ValueError:
            await callback.answer("Неизвестный фокус", show_alert=True)
            return

        data = await state.get_data()
        try:
            style = MotivationStyle(data.get("motivation", "supportive"))
        except ValueError:
            style = MotivationStyle.SUPPORTIVE

        await complete_onboarding.execute(callback.from_user.id, style, focus)
        await state.clear()
        await callback.message.edit_text(
            f"Готово!\n\n"
            f"🎨 Стиль коуча: {style.label}\n"
            f"⭐ Приоритет: {focus.label}\n\n"
            "Можешь поменять это в любой момент в ⚙️ Настройки → 🎨 Стиль коуча."
        )
        await callback.message.answer(
            "Теперь создай первую привычку через ➕ или просто опиши,"
            " что хочешь делать — я разберусь сам.",
            reply_markup=main_menu(),
        )
        await callback.answer()

    # ────────  Смена стиля из настроек ────────

    @router.callback_query(F.data == "set:motivation")
    async def show_motivation_picker(callback: CallbackQuery) -> None:
        user = await users.get(callback.from_user.id)
        current = user.motivation_style.label if user else "не задан"
        await callback.message.edit_text(
            f"🎨 Текущий стиль: {current}\n\nВыбери новый:",
            reply_markup=motivation_kb(prefix="setmot"),
        )

    @router.callback_query(F.data.startswith("setmot:"))
    async def change_motivation(callback: CallbackQuery) -> None:
        raw = callback.data.split(":", 1)[1]
        try:
            style = MotivationStyle(raw)
        except ValueError:
            await callback.answer("Неизвестный стиль", show_alert=True)
            return
        await update_motivation.execute(callback.from_user.id, style)
        await callback.message.edit_text(
            f"✅ Стиль коуча обновлён: {style.label}\n_{style.description}_",
            parse_mode="Markdown",
        )
        await callback.answer()

    return router
