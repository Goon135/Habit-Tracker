"""Хэндлеры по привычкам: создание / список / отметка / удаление.

Расширенный flow создания (фичи #2, #6):
1. Название
2. Категория
3. Тип: булевая или количественная
   - если количественная: целевое значение + единица измерения
4. Цель или постоянная привычка
   - если цель: длительность

Отметка количественной (#2) — отдельным шагом просит ввести фактическое значение.
"""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.application.use_cases.create_habit import CreateHabitUseCase
from src.application.use_cases.get_today_progress import GetTodayProgressUseCase
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.value_objects.category import Category
from src.presentation.handlers.states import AddHabit, CompleteQuantitative
from src.presentation.keyboards.keyboards import (
    category_kb,
    goal_duration_kb,
    habit_goal_kb,
    habit_type_kb,
    habits_list_kb,
)


def _progress_bar(ratio: float, width: int = 10) -> str:
    """ASCII-прогресс-бар: ▰▰▰▰▱▱▱▱▱▱"""
    ratio = max(0.0, min(1.0, ratio))
    filled = int(round(ratio * width))
    return "▰" * filled + "▱" * (width - filled)


def _format_progress_line(p) -> str:
    """Строка прогресса для списка привычек."""
    icon = "🔥" if p.streak >= 3 else "📌"
    goal_tag = "🎯 " if p.is_goal else ""
    line = f"{icon} {goal_tag}{p.name} ({p.category})"
    if p.is_quantitative:
        bar = _progress_bar(p.progress_ratio)
        unit = p.unit or ""
        line += f"\n   {bar} {p.current_value:g}/{p.target_value:g} {unit}".rstrip()
    if p.is_goal and p.end_date is not None:
        days_left = (p.end_date - date.today()).days
        if days_left >= 0:
            line += f"\n   📅 Осталось дней: {days_left}"
    line += f"\n   Серия: {p.streak} дн."
    return line


def _format_completion_result(habit_name: str, result) -> str:
    """Форматирует результат отметки. Для количественных — с прогресс-баром."""
    lines = []
    if result.target_value is not None:
        bar = _progress_bar(result.progress_ratio)
        unit = result.unit or ""
        lines.append(f"🔢 «{habit_name}»")
        lines.append(
            f"{bar} {result.current_value:g}/{result.target_value:g} {unit}".rstrip()
        )
        if result.completed:
            lines.append("✅ Цель на сегодня достигнута!")
        else:
            remaining = max(result.target_value - result.current_value, 0)
            lines.append(f"⏳ Осталось: {remaining:g} {unit}".rstrip())
    else:
        lines.append(f"✅ Отмечено: «{habit_name}»")

    if result.completed:
        lines.append("")
        lines.append(f"🔥 Серия: {result.streak} дн.")
        lines.append(
            f"⭐ +{result.points_earned} очков (всего: {result.total_points})"
        )
        lines.append(f"📊 Уровень: {result.level} ({result.level_title})")
        for ach in result.new_achievements:
            lines.append("")
            lines.append(f"🏅 Новое достижение: {ach['title']}")
            lines.append(ach["desc"])
    return "\n".join(lines)


def build_router(
    create_habit: CreateHabitUseCase,
    complete_habit: CompleteHabitUseCase,
    today_progress: GetTodayProgressUseCase,
    habits_repo: HabitRepository,
) -> Router:
    router = Router(name="habits")

    # ──────── Создание ────────

    @router.message(F.text == "➕ Новая привычка")
    @router.message(Command("new"))
    async def start_new(message: Message, state: FSMContext) -> None:
        await state.set_state(AddHabit.waiting_name)
        await message.answer(
            "✏️ Название новой привычки?\n"
            "Например: «Бегать 30 минут», «Читать 20 страниц», «Медитация»\n\n"
            "Подсказка: если у тебя сразу несколько идей — отправь обычным текстом или "
            "голосовым, и я разберу их сам."
        )

    @router.message(AddHabit.waiting_name)
    async def name_entered(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("Пустое название не подойдёт, попробуй ещё раз.")
            return
        await state.update_data(name=name)
        await state.set_state(AddHabit.waiting_category)
        await message.answer("📂 Выбери категорию:", reply_markup=category_kb())

    @router.callback_query(AddHabit.waiting_category, F.data.startswith("cat:"))
    async def category_chosen(callback: CallbackQuery, state: FSMContext) -> None:
        category = Category.from_string(callback.data.split(":", 1)[1])
        await state.update_data(category=category.value)
        await state.set_state(AddHabit.waiting_quantitative_choice)
        await callback.message.edit_text(
            f"📂 Категория: {category.value}\n\n"
            "🔢 Это обычная привычка (выполнил/не выполнил) или количественная "
            "(например, «3 литра воды», «10 000 шагов», «30 минут чтения»)?",
            reply_markup=habit_type_kb(),
        )
        await callback.answer()

    @router.callback_query(AddHabit.waiting_quantitative_choice, F.data == "qtype:bool")
    async def chose_boolean(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AddHabit.waiting_goal_choice)
        await callback.message.edit_text(
            "🎯 Это постоянная привычка или цель на ограниченный срок?",
            reply_markup=habit_goal_kb(),
        )
        await callback.answer()

    @router.callback_query(AddHabit.waiting_quantitative_choice, F.data == "qtype:quant")
    async def chose_quantitative(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AddHabit.waiting_target_value)
        await callback.message.edit_text(
            "🔢 Какое целевое значение в день?\n"
            "Введи число. Например: 3 (литра воды), 10000 (шагов), 30 (минут)."
        )
        await callback.answer()

    @router.message(AddHabit.waiting_target_value)
    async def target_entered(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip().replace(",", ".")
        try:
            value = float(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Нужно положительное число. Попробуй ещё раз.")
            return
        await state.update_data(target_value=value)
        await state.set_state(AddHabit.waiting_unit)
        await message.answer(
            "📏 Единица измерения? Например: л, мл, минут, страниц, шагов, км.\n"
            "Если не нужно — отправь «-»."
        )

    @router.message(AddHabit.waiting_unit)
    async def unit_entered(message: Message, state: FSMContext) -> None:
        unit = (message.text or "").strip()
        if unit == "-" or not unit:
            unit = None
        await state.update_data(unit=unit)
        await state.set_state(AddHabit.waiting_goal_choice)
        await message.answer(
            "🎯 Это постоянная привычка или цель на ограниченный срок?",
            reply_markup=habit_goal_kb(),
        )

    async def _finalize_creation(
        event,
        state: FSMContext,
        is_goal: bool,
        end_date: date | None,
    ) -> None:
        data = await state.get_data()
        name = data["name"]
        category = Category.from_string(data.get("category", "Общее"))
        target_value = data.get("target_value")
        unit = data.get("unit")

        user_id = event.from_user.id
        habit = await create_habit.execute(
            user_id=user_id,
            name=name,
            category=category,
            target_value=target_value,
            unit=unit,
            is_goal=is_goal,
            end_date=end_date,
        )
        await state.clear()

        lines = [f"✅ {'Цель' if is_goal else 'Привычка'} «{habit.name}» создана!"]
        lines.append(f"📂 Категория: {habit.category.value}")
        if habit.is_quantitative:
            lines.append(f"🔢 Цель в день: {habit.target_value:g} {habit.unit or ''}".rstrip())
        if is_goal and end_date:
            days_left = (end_date - date.today()).days
            lines.append(f"📅 Дедлайн: {end_date.isoformat()} (через {days_left} дн.)")
        text = "\n".join(lines)

        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text)
            await event.answer()
        else:
            await event.answer(text)

    @router.callback_query(AddHabit.waiting_goal_choice, F.data == "gtype:habit")
    async def chose_habit(callback: CallbackQuery, state: FSMContext) -> None:
        await _finalize_creation(callback, state, is_goal=False, end_date=None)

    @router.callback_query(AddHabit.waiting_goal_choice, F.data == "gtype:goal")
    async def chose_goal(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(AddHabit.waiting_goal_duration)
        await callback.message.edit_text(
            "📅 На сколько дней ставим цель?",
            reply_markup=goal_duration_kb(),
        )
        await callback.answer()

    @router.callback_query(AddHabit.waiting_goal_duration, F.data.startswith("gdur:"))
    async def goal_duration_chosen(callback: CallbackQuery, state: FSMContext) -> None:
        raw = callback.data.split(":", 1)[1]
        if raw == "custom":
            await callback.message.edit_text("Введи число дней (например, 14):")
            await callback.answer()
            return
        try:
            days = int(raw)
        except ValueError:
            await callback.answer("Ошибка длительности", show_alert=True)
            return
        end_date = date.today() + timedelta(days=days)
        await _finalize_creation(callback, state, is_goal=True, end_date=end_date)

    @router.message(AddHabit.waiting_goal_duration)
    async def goal_duration_custom(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        try:
            days = int(raw)
            if days <= 0 or days > 3650:
                raise ValueError
        except ValueError:
            await message.answer("Нужно целое число дней от 1 до 3650.")
            return
        end_date = date.today() + timedelta(days=days)
        await _finalize_creation(message, state, is_goal=True, end_date=end_date)

    # ──────── Список ────────

    @router.message(F.text == "📋 Мои привычки")
    async def show_my_habits(message: Message) -> None:
        progress = await today_progress.execute(message.from_user.id)
        habits = [p for p in progress if not p.is_goal]
        if not habits:
            await message.answer("У тебя пока нет привычек. Создай первую через ➕.")
            return
        lines = ["📋 Твои привычки:\n"]
        for p in habits:
            lines.append(_format_progress_line(p))
            lines.append("")
        await message.answer("\n".join(lines))

    @router.message(F.text == "🎯 Мои цели")
    async def show_my_goals(message: Message) -> None:
        progress = await today_progress.execute(message.from_user.id)
        goals = [p for p in progress if p.is_goal]
        if not goals:
            await message.answer(
                "У тебя пока нет активных целей.\n\n"
                "При создании привычки выбери вариант «🎯 Цель» — это даст дедлайн."
            )
            return
        lines = ["🎯 Твои цели:\n"]
        for p in goals:
            lines.append(_format_progress_line(p))
            lines.append("")
        await message.answer("\n".join(lines))

    # ──────── Отметка ────────

    @router.message(F.text == "✅ Отметить сегодня")
    @router.message(Command("today"))
    async def show_today(message: Message) -> None:
        progress = await today_progress.execute(message.from_user.id)
        if not progress:
            await message.answer("У тебя пока нет привычек.")
            return
        lines = ["📅 Сегодня:\n"]
        pending: list = []
        for p in progress:
            mark = "✅" if p.completed_today else "⬜"
            if p.is_quantitative:
                bar = _progress_bar(p.progress_ratio, width=6)
                lines.append(
                    f"  {mark} {p.name}  {bar} "
                    f"{p.current_value:g}/{p.target_value:g} {p.unit or ''}".rstrip()
                )
            else:
                lines.append(f"  {mark} {p.name}")
            if not p.completed_today:
                pending.append(p)
        await message.answer("\n".join(lines))
        if not pending:
            await message.answer("🎉 Всё выполнено на сегодня. Молодец!")
            return

        all_habits = await habits_repo.list_for_user(message.from_user.id)
        pending_ids = {p.habit_id for p in pending}
        pending_habits = [h for h in all_habits if h.id in pending_ids]
        await message.answer(
            "Отметь выполненные:",
            reply_markup=habits_list_kb(pending_habits, action="done"),
        )

    @router.callback_query(F.data.startswith("done:"))
    async def mark_done(callback: CallbackQuery, state: FSMContext) -> None:
        habit_id = int(callback.data.split(":")[1])
        habit = await habits_repo.get(habit_id)
        if habit is None or habit.user_id != callback.from_user.id:
            await callback.answer("Привычка не найдена", show_alert=True)
            return

        if habit.is_quantitative:
            await state.set_state(CompleteQuantitative.waiting_value)
            await state.update_data(habit_id=habit_id)
            unit = habit.unit or ""
            await callback.message.answer(
                f"🔢 Сколько добавить к «{habit.name}»?\n"
                f"Цель в день: {habit.target_value:g} {unit}.\n"
                f"Введи число (можно дробное, разделитель — точка или запятая)."
            )
            await callback.answer()
            return

        result = await complete_habit.execute(callback.from_user.id, habit_id)
        await callback.message.edit_text(_format_completion_result(habit.name, result))
        await callback.answer()

    @router.message(CompleteQuantitative.waiting_value)
    async def quantitative_value_entered(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip().replace(",", ".")
        try:
            value = float(raw)
            if value <= 0:
                raise ValueError
        except ValueError:
            await message.answer("Нужно положительное число. Попробуй ещё раз.")
            return
        data = await state.get_data()
        habit_id = data["habit_id"]
        habit = await habits_repo.get(habit_id)
        await state.clear()
        if habit is None or habit.user_id != message.from_user.id:
            await message.answer("Привычка не найдена.")
            return
        result = await complete_habit.execute(message.from_user.id, habit_id, value=value)
        await message.answer(_format_completion_result(habit.name, result))

    # ──────── Удаление ────────

    @router.callback_query(F.data == "set:delete")
    async def delete_menu(callback: CallbackQuery) -> None:
        habits = await habits_repo.list_for_user(callback.from_user.id)
        if not habits:
            await callback.message.edit_text("Нет активных привычек.")
            return
        await callback.message.edit_text(
            "🗑 Выбери привычку для удаления:",
            reply_markup=habits_list_kb(habits, action="del"),
        )

    @router.callback_query(F.data.startswith("del:"))
    async def delete_confirm(callback: CallbackQuery) -> None:
        habit_id = int(callback.data.split(":")[1])
        await habits_repo.deactivate(habit_id, callback.from_user.id)
        await callback.message.edit_text("🗑 Привычка удалена.")
        await callback.answer()

    return router
