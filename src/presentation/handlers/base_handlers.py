"""Базовые команды: /start, /help, профиль."""
from __future__ import annotations

from typing import Callable

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.application.use_cases.register_user import RegisterUserUseCase
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.repositories.other_repositories import AchievementRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.services.gamification import get_level_title
from src.domain.value_objects.coaching_mode import CoachingMode
from src.presentation.keyboards.keyboards import main_menu


def build_router(
    register_user: RegisterUserUseCase,
    users: UserRepository,
    habits: HabitRepository,
    achievements: AchievementRepository,
    start_onboarding: Callable | None = None,
) -> Router:
    """start_onboarding — функция запуска онбординг-опроса (импортируется
    из onboarding_handlers). Передаётся через DI снаружи, чтобы избежать
    циклической зависимости между роутерами."""
    router = Router(name="base")

    @router.message(CommandStart())
    async def cmd_start(message: Message, state: FSMContext) -> None:
        user = await register_user.execute(
            message.from_user.id,
            message.from_user.username or "",
            message.from_user.first_name or "",
        )

        # Если онбординг не пройден — приветствие + сразу опрос.
        if not user.onboarding_completed and start_onboarding is not None:
            await message.answer(
                f"👋 Привет, {message.from_user.first_name}!\n\n"
                "Я — трекер привычек с AI-коучем, голосовым вводом и анализом настроения.",
                reply_markup=main_menu(),
            )
            await start_onboarding(message, state)
            return

        # Иначе обычное приветствие.
        mode_hint = (
            "🤖 Тебе доступен AI-коуч — кнопка «💬 AI-коуч»."
            if user.coaching_mode == CoachingMode.LLM
            else "📋 Поддержка через короткие подсказки."
        )
        await message.answer(
            f"👋 С возвращением, {message.from_user.first_name}!\n\n"
            f"{mode_hint}",
            reply_markup=main_menu(),
        )

    @router.message(Command("help"))
    async def cmd_help(message: Message) -> None:
        await message.answer(
            "📖 Команды:\n\n"
            "/start — начать\n"
            "/help — помощь\n"
            "/onboarding — пройти опрос заново\n"
            "/today — статус на сегодня\n"
            "/stats — статистика\n"
            "/insights — AI-аналитика (раз в 4 часа)\n"
            "/recovery — режим восстановления при выгорании\n"
            "/coach — AI-коуч\n"
            "/mood — отметить настроение\n"
            "/insights — корреляция привычек и настроения\n"
            "/export — экспорт отчёта\n"
            "/profile — профиль\n\n"
            "Также можешь просто отправить голосовое сообщение или текст вида "
            "«хочу начать бегать и читать перед сном» — бот сам разберётся.",
            reply_markup=main_menu(),
        )

    @router.message(Command("profile"))
    async def cmd_profile(message: Message) -> None:
        user = await users.get(message.from_user.id)
        if user is None:
            await message.answer("Сначала нажми /start")
            return
        habit_list = await habits.list_for_user(user.id)
        achs = await achievements.list_for_user(user.id)
        style_line = ""
        if user.onboarding_completed:
            style_line = (
                f"\n🎨 Стиль коуча: {user.motivation_style.label}\n"
                f"⭐ Приоритет: {user.priority_focus.label}"
            )
        await message.answer(
            f"👤 Профиль\n\n"
            f"Имя: {user.first_name}\n"
            f"⭐ Очки: {user.points}\n"
            f"📈 Уровень: {user.level} ({get_level_title(user.level)})\n"
            f"📋 Привычек: {len(habit_list)}\n"
            f"🎖 Достижений: {len(achs)}\n"
            f"🧪 A/B группа: {user.coaching_mode.value}"
            f"{style_line}",
        )

    return router
