"""Настройки (время напоминаний) + достижения."""
from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.domain.repositories.other_repositories import AchievementRepository
from src.domain.repositories.user_repository import UserRepository
from src.presentation.handlers.states import SetReminder
from src.presentation.keyboards.keyboards import main_menu, settings_kb


def build_router(
    users: UserRepository,
    achievements: AchievementRepository,
) -> Router:
    router = Router(name="settings")

    # ──────── Settings ────────

    @router.message(F.text == "⚙️ Настройки")
    async def show_settings(message: Message) -> None:
        user = await users.get(message.from_user.id)
        if user is None:
            await message.answer("Сначала /start.")
            return
        await message.answer(
            f"⚙️ Настройки\n\n⏰ Время напоминаний: {user.reminder_time.strftime('%H:%M')}",
            reply_markup=settings_kb(),
        )

    @router.callback_query(F.data == "set:reminder")
    async def start_set_reminder(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(SetReminder.waiting_time)
        await callback.message.edit_text(
            "⏰ Введи время напоминаний в формате ЧЧ:ММ\nНапример: 09:00 или 21:30"
        )

    @router.message(SetReminder.waiting_time)
    async def finish_set_reminder(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            h, m = raw.split(":")
            new_time = time(int(h), int(m))
        except (ValueError, IndexError):
            await message.answer("❌ Неверный формат. Пример: 09:00")
            return

        user = await users.get(message.from_user.id)
        if user is None:
            await state.clear()
            await message.answer("Сначала /start.")
            return

        user.change_reminder_time(new_time)
        await users.save(user)
        await state.clear()
        await message.answer(
            f"✅ Напоминания установлены на {new_time.strftime('%H:%M')}",
            reply_markup=main_menu(),
        )

    # ──────── Achievements ────────

    @router.message(F.text == "🎖 Достижения")
    @router.message(Command("achievements"))
    async def show_achievements(message: Message) -> None:
        achs = await achievements.list_for_user(message.from_user.id)
        if not achs:
            await message.answer(
                "🎖 У тебя пока нет достижений.\n\n"
                "Выполняй привычки каждый день, чтобы получить первое!"
            )
            return
        lines = ["🎖 Твои достижения:\n"]
        for a in achs:
            lines.append(f"  {a.title}\n  {a.description}\n")
        await message.answer("\n".join(lines))

    return router
