"""Настроение: отметка 1–5 и инсайты."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from src.application.use_cases.mood import LogMoodUseCase, MoodCorrelationUseCase
from src.presentation.keyboards.keyboards import mood_kb


def build_router(
    log_mood: LogMoodUseCase,
    correlation: MoodCorrelationUseCase,
) -> Router:
    router = Router(name="mood")

    @router.message(F.text == "😊 Настроение")
    @router.message(Command("mood"))
    async def show_mood_picker(message: Message) -> None:
        await message.answer(
            "Как сегодня настроение? Выбери оценку от 1 (плохо) до 5 (отлично):",
            reply_markup=mood_kb(),
        )

    @router.callback_query(F.data.startswith("mood:"))
    async def save_mood(callback: CallbackQuery) -> None:
        score = int(callback.data.split(":")[1])
        await log_mood.execute(callback.from_user.id, score)
        await callback.message.edit_text(f"Записано: {score}/5. Спасибо!")
        await callback.answer()

    @router.message(Command("insights"))
    async def show_insights(message: Message) -> None:
        insights = await correlation.execute(message.from_user.id, days=30)
        if not insights:
            await message.answer(
                "Пока недостаточно данных. Нужно хотя бы 3 отметки настроения за месяц "
                "и привычки с историей выполнения."
            )
            return
        lines = ["📊 Связь привычек и настроения (за 30 дней):\n"]
        for ins in insights[:10]:
            sign = "+" if ins.delta >= 0 else ""
            lines.append(
                f"• {ins.habit_name}\n"
                f"  В дни выполнения: {ins.avg_mood_when_done}/5\n"
                f"  В дни без неё:    {ins.avg_mood_when_skipped}/5\n"
                f"  Разница: {sign}{ins.delta}\n"
            )
        await message.answer("\n".join(lines))

    return router
