"""Точка входа: собирает Container, регистрирует роутеры, запускает aiogram + scheduler.

Запуск:
    python -m src
или после установки пакета:
    habitbot
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from src.infrastructure.config import Settings
from src.infrastructure.container import Container
from src.presentation.handlers import (
    base_handlers,
    coach_handlers,
    edit_habit_handlers,
    export_handlers,
    habit_handlers,
    insights_handlers,
    mood_handlers,
    onboarding_handlers,
    settings_handlers,
    voice_handlers,
)


async def run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log = logging.getLogger("habitbot")

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    container = Container(settings, bot)

    dp = Dispatcher(storage=MemoryStorage())
    uc = container.use_cases

    # Сначала — онбординг-роутер. Нужен, чтобы base_handlers мог инжектить
    # функцию запуска опроса через DI, не создавая циклической зависимости.
    onboarding_router = onboarding_handlers.build_router(
        complete_onboarding=uc.complete_onboarding,
        update_motivation=uc.update_motivation_style,
        users=container.users,
    )
    start_questionnaire = getattr(onboarding_router, "start_questionnaire", None)

    # Порядок включения роутеров важен:
    # - онбординг до coach, чтобы callback'и опроса не попали в free_text_fallback.
    # - voice до coach, иначе voice-message не попадёт в обработчик.
    # - coach со свободным текстом — последним.
    # - habit_handlers ДО edit_habit_handlers — иначе callback'и done:/del:/edit: ловит не тот.
    dp.include_router(base_handlers.build_router(
        register_user=uc.register_user,
        users=container.users,
        habits=container.habits,
        achievements=container.achievements,
        start_onboarding=start_questionnaire,
    ))
    dp.include_router(onboarding_router)
    dp.include_router(habit_handlers.build_router(
        create_habit=uc.create_habit,
        complete_habit=uc.complete_habit,
        today_progress=uc.today_progress,
        habits_repo=container.habits,
    ))
    dp.include_router(edit_habit_handlers.build_router(
        update_habit=uc.update_habit,
        habits_repo=container.habits,
    ))
    dp.include_router(mood_handlers.build_router(
        log_mood=uc.log_mood,
        correlation=uc.mood_correlation,
    ))
    dp.include_router(insights_handlers.build_router(
        generate_insights=uc.generate_insights,
        assess_burnout=uc.assess_burnout,
        toggle_recovery=uc.toggle_recovery,
        users=container.users,
    ))
    dp.include_router(export_handlers.build_router(exporter=container.exporter))
    dp.include_router(settings_handlers.build_router(
        users=container.users,
        achievements=container.achievements,
    ))
    dp.include_router(voice_handlers.build_router(bot=bot, process_voice=uc.process_voice))
    dp.include_router(coach_handlers.build_router(
        coach_reply=uc.coach_reply,
        extract_habits=uc.extract_habits,
        users=container.users,
    ))

    container.scheduler.start()

    log.info("🔥 Прогреваем LLM (это займёт 10-30 секунд)...")
    try:
        await container.llm_coach.reply(
            user_message="ping",
            history=[],
            user_context={"first_name": "system", "habits": []},
        )
        log.info("✅ LLM готова")
    except Exception as exc:
        log.warning("LLM warmup failed (will retry on first user request): %s", exc)

    log.info("🚀 Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        await container.dispose()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
