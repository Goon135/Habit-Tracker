"""Хэндлеры редактирования привычек (#5).

Flow:
1. «✏️ Изменить привычку» → выбрать какую
2. → выбрать поле для изменения (название / категория / цель / единица / дедлайн)
3. → ввести новое значение
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from src.application.use_cases.update_habit import (
    UNSET,
    UpdateHabitFields,
    UpdateHabitUseCase,
)
from src.domain.repositories.habit_repository import HabitRepository
from src.domain.value_objects.category import Category
from src.presentation.handlers.states import EditHabit
from src.presentation.keyboards.keyboards import (
    category_kb,
    edit_field_kb,
    habits_list_kb,
)


def build_router(
    update_habit: UpdateHabitUseCase,
    habits_repo: HabitRepository,
) -> Router:
    router = Router(name="edit_habit")

    @router.message(F.text == "✏️ Изменить привычку")
    async def start_edit(message: Message, state: FSMContext) -> None:
        habits = await habits_repo.list_for_user(message.from_user.id)
        if not habits:
            await message.answer("У тебя пока нет привычек. Создай первую через ➕.")
            return
        await state.set_state(EditHabit.choosing_habit)
        await message.answer(
            "✏️ Какую привычку поменять?",
            reply_markup=habits_list_kb(habits, action="edit"),
        )

    @router.callback_query(EditHabit.choosing_habit, F.data.startswith("edit:"))
    async def chose_habit(callback: CallbackQuery, state: FSMContext) -> None:
        habit_id = int(callback.data.split(":")[1])
        habit = await habits_repo.get(habit_id)
        if habit is None or habit.user_id != callback.from_user.id:
            await callback.answer("Привычка не найдена", show_alert=True)
            return
        await state.update_data(habit_id=habit_id)
        await state.set_state(EditHabit.choosing_field)
        info_lines = [
            f"Редактируем: «{habit.name}»",
            f"Категория: {habit.category.value}",
        ]
        if habit.is_quantitative:
            info_lines.append(
                f"Цель: {habit.target_value:g} {habit.unit or ''}".rstrip()
            )
        if habit.is_goal and habit.end_date:
            info_lines.append(f"Дедлайн: {habit.end_date.isoformat()}")
        await callback.message.edit_text(
            "\n".join(info_lines) + "\n\nЧто поменять?",
            reply_markup=edit_field_kb(),
        )
        await callback.answer()

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:cancel")
    async def cancel_edit(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_text("Изменение отменено.")
        await callback.answer()

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:name")
    async def edit_name(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(EditHabit.waiting_new_name)
        await callback.message.edit_text("✏️ Введи новое название:")
        await callback.answer()

    @router.message(EditHabit.waiting_new_name)
    async def save_new_name(message: Message, state: FSMContext) -> None:
        name = (message.text or "").strip()
        if not name:
            await message.answer("Пустое название не подойдёт.")
            return
        data = await state.get_data()
        await update_habit.execute(
            message.from_user.id, data["habit_id"], UpdateHabitFields(name=name),
        )
        await state.clear()
        await message.answer(f"✅ Название изменено: «{name}»")

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:category")
    async def edit_category(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(EditHabit.waiting_new_category)
        await callback.message.edit_text("📂 Выбери новую категорию:", reply_markup=category_kb())
        await callback.answer()

    @router.callback_query(EditHabit.waiting_new_category, F.data.startswith("cat:"))
    async def save_new_category(callback: CallbackQuery, state: FSMContext) -> None:
        category = Category.from_string(callback.data.split(":", 1)[1])
        data = await state.get_data()
        await update_habit.execute(
            callback.from_user.id, data["habit_id"], UpdateHabitFields(category=category),
        )
        await state.clear()
        await callback.message.edit_text(f"✅ Категория изменена: {category.value}")
        await callback.answer()

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:target")
    async def edit_target(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(EditHabit.waiting_new_target)
        await callback.message.edit_text(
            "🔢 Введи новое целевое значение в день (число).\n"
            "Чтобы сделать привычку обычной (без числа) — отправь «0»."
        )
        await callback.answer()

    @router.message(EditHabit.waiting_new_target)
    async def save_new_target(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip().replace(",", ".")
        try:
            value = float(raw)
        except ValueError:
            await message.answer("Нужно число. Попробуй ещё раз.")
            return
        data = await state.get_data()
        # value == 0 → делаем привычку обычной (target_value=None, unit=None).
        if value == 0:
            await update_habit.execute(
                message.from_user.id,
                data["habit_id"],
                UpdateHabitFields(target_value=None, unit=None),
            )
            await state.clear()
            await message.answer("✅ Привычка переведена в обычный режим (без количественной цели).")
            return
        if value < 0:
            await message.answer("Значение должно быть >= 0.")
            return
        await update_habit.execute(
            message.from_user.id, data["habit_id"], UpdateHabitFields(target_value=value),
        )
        await state.clear()
        await message.answer(f"✅ Целевое значение: {value:g}")

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:unit")
    async def edit_unit(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(EditHabit.waiting_new_unit)
        await callback.message.edit_text(
            "📏 Введи новую единицу измерения (л, минут, страниц…).\n"
            "Чтобы убрать — отправь «-»."
        )
        await callback.answer()

    @router.message(EditHabit.waiting_new_unit)
    async def save_new_unit(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        unit = None if raw == "-" or not raw else raw
        data = await state.get_data()
        await update_habit.execute(
            message.from_user.id, data["habit_id"], UpdateHabitFields(unit=unit),
        )
        await state.clear()
        await message.answer(f"✅ Единица измерения: {unit or '(не задана)'}")

    @router.callback_query(EditHabit.choosing_field, F.data == "ef:end_date")
    async def edit_end_date(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(EditHabit.waiting_new_end_date)
        await callback.message.edit_text(
            "🗓 Новый дедлайн.\n\n"
            "Можно ввести:\n"
            "• Число дней от сегодня (например, 30)\n"
            "• Дату в формате ГГГГ-ММ-ДД (например, 2026-07-01)\n"
            "• «-» чтобы убрать дедлайн (привычка перестанет быть целью)"
        )
        await callback.answer()

    @router.message(EditHabit.waiting_new_end_date)
    async def save_new_end_date(message: Message, state: FSMContext) -> None:
        raw = (message.text or "").strip()
        data = await state.get_data()

        if raw == "-":
            await update_habit.execute(
                message.from_user.id,
                data["habit_id"],
                UpdateHabitFields(is_goal=False, end_date=None),
            )
            await state.clear()
            await message.answer("✅ Дедлайн убран, привычка стала постоянной.")
            return

        # Сначала пробуем как число дней.
        new_date: date | None = None
        try:
            days = int(raw)
            if days > 0:
                new_date = date.today() + timedelta(days=days)
        except ValueError:
            pass

        if new_date is None:
            # Пробуем как дату.
            try:
                new_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                await message.answer(
                    "Не понял формат. Введи число дней, дату ГГГГ-ММ-ДД или «-»."
                )
                return

        if new_date < date.today():
            await message.answer("Дата должна быть сегодня или позже.")
            return

        try:
            await update_habit.execute(
                message.from_user.id,
                data["habit_id"],
                UpdateHabitFields(is_goal=True, end_date=new_date),
            )
        except ValueError as exc:
            await message.answer(f"Ошибка: {exc}")
            return
        await state.clear()
        days_left = (new_date - date.today()).days
        await message.answer(
            f"✅ Дедлайн: {new_date.isoformat()} (через {days_left} дн.)"
        )

    return router
