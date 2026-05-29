"""Хэндлеры для /insights и /recovery (фичи #1, #2, #3).

/insights — показывает персональную аналитику. Если данных мало —
честно сообщает об этом. Ratelimit: не чаще раза в 4 часа (LLM-вызов
дорогой).

/recovery — статус recovery mode. Из меню можно включить на 3 дня
или выключить досрочно.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from src.application.use_cases.burnout import (
    AssessBurnoutRiskUseCase,
    ToggleRecoveryModeUseCase,
)
from src.application.use_cases.generate_insights import GenerateInsightsUseCase
from src.domain.repositories.user_repository import UserRepository


INSIGHT_COOLDOWN_HOURS = 4


def _recovery_kb(in_recovery: bool) -> InlineKeyboardMarkup:
    if in_recovery:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚪 Выйти из режима", callback_data="rec:exit")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌿 Включить на 3 дня", callback_data="rec:enter:3")],
        [InlineKeyboardButton(text="🌿 На 7 дней", callback_data="rec:enter:7")],
    ])


def build_router(
    generate_insights: GenerateInsightsUseCase,
    assess_burnout: AssessBurnoutRiskUseCase,
    toggle_recovery: ToggleRecoveryModeUseCase,
    users: UserRepository,
) -> Router:
    router = Router(name="insights")

    # ──────── /insights ────────

    @router.message(F.text == "🧠 Insights")
    @router.message(Command("insights"))
    async def cmd_insights(message: Message) -> None:
        user = await users.get(message.from_user.id)
        if user is None:
            await message.answer("Сначала /start")
            return

        # Ratelimit.
        if user.last_insight_at is not None:
            elapsed = datetime.utcnow() - user.last_insight_at
            if elapsed < timedelta(hours=INSIGHT_COOLDOWN_HOURS):
                left = timedelta(hours=INSIGHT_COOLDOWN_HOURS) - elapsed
                hrs = int(left.total_seconds() // 3600)
                mins = int((left.total_seconds() % 3600) // 60)
                await message.answer(
                    f"⏱ Свежий инсайт уже считался недавно.\n"
                    f"Следующий — через {hrs}ч {mins}мин.\n\n"
                    f"Чтобы посмотреть прошлый — /stats."
                )
                return

        await message.answer("🧠 Считаю аналитику... это займёт ~5-10 секунд.")
        insight = await generate_insights.execute(message.from_user.id)
        if insight is None:
            await message.answer(
                "📭 Данных пока мало для содержательного инсайта.\n\n"
                "Нужно хотя бы несколько дней с отметками привычек. "
                "Возвращайся через недельку!"
            )
            return

        # Также сразу оцениваем burnout-риск.
        risk = await assess_burnout.execute(message.from_user.id)

        text_parts = [
            f"📊 Аналитика за {insight.period_days} дней\n",
            insight.summary_text,
            "",
            "📅 Heatmap активности:",
            f"```\n{insight.heatmap_ascii}\n```",
        ]
        if risk.level != "low":
            text_parts.extend([
                "",
                f"{risk.level_emoji} Риск спада: {risk.level_label} ({risk.score}/100)",
            ])
            if risk.factors:
                text_parts.append("Факторы: " + "; ".join(risk.factors[:3]))
            if risk.level == "high":
                text_parts.append("")
                text_parts.append(
                    "💡 Рассмотри режим восстановления: /recovery"
                )

        if not insight.formatted_by_llm:
            text_parts.append("\n_(текст сформирован шаблоном — LLM временно недоступна)_")

        await message.answer("\n".join(text_parts), parse_mode="Markdown")

    # ──────── /recovery ────────

    @router.message(F.text == "🌿 Восстановление")
    @router.message(Command("recovery"))
    async def cmd_recovery(message: Message) -> None:
        status = await toggle_recovery.status(message.from_user.id)
        risk = await assess_burnout.execute(message.from_user.id)

        if status.is_active:
            text = (
                f"🌿 Режим восстановления активен\n\n"
                f"Действует до: {status.until.isoformat()}\n"
                f"Осталось: {status.days_left} дн.\n\n"
                "Что меняется:\n"
                "• цели снижены на 30%\n"
                "• напоминания отключены\n"
                "• коуч в мягком тоне"
            )
        else:
            text_parts = [
                "🌿 Режим восстановления\n",
                f"Текущий риск спада: {risk.level_emoji} {risk.level_label} ({risk.score}/100)",
            ]
            if risk.factors:
                text_parts.append("\nЗамечено:")
                for f in risk.factors[:4]:
                    text_parts.append(f"• {f}")
            text_parts.extend([
                "",
                "В режиме восстановления:",
                "• целевые значения снижаются на 30%",
                "• напоминания не приходят",
                "• коуч мягче и не давит",
                "",
                "Это нормально — иногда нужна пауза.",
            ])
            text = "\n".join(text_parts)

        await message.answer(text, reply_markup=_recovery_kb(status.is_active))

    @router.callback_query(F.data.startswith("rec:enter:"))
    async def on_enter(callback: CallbackQuery) -> None:
        try:
            days = int(callback.data.split(":")[2])
        except (IndexError, ValueError):
            await callback.answer("Ошибка", show_alert=True)
            return
        state = await toggle_recovery.enter(callback.from_user.id, days=days)
        await callback.message.edit_text(
            f"🌿 Режим восстановления включён до {state.until.isoformat()} "
            f"({state.days_left} дн.).\n\n"
            "Не торопись, береги себя. В любой момент можно выйти: /recovery"
        )
        await callback.answer()

    @router.callback_query(F.data == "rec:exit")
    async def on_exit(callback: CallbackQuery) -> None:
        await toggle_recovery.exit(callback.from_user.id)
        await callback.message.edit_text(
            "✅ Режим восстановления выключен. Возвращаемся к обычному режиму."
        )
        await callback.answer()

    return router
