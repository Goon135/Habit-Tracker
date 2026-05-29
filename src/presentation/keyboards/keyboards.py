"""Клавиатуры — выделены отдельно от хэндлеров."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from src.domain.entities.habit import Habit
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Мои привычки"), KeyboardButton(text="➕ Новая привычка")],
            [KeyboardButton(text="🎯 Мои цели"), KeyboardButton(text="✏️ Изменить привычку")],
            [KeyboardButton(text="✅ Отметить сегодня"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🧠 Insights"), KeyboardButton(text="🌿 Восстановление")],
            [KeyboardButton(text="💬 AI-коуч"), KeyboardButton(text="😊 Настроение")],
            [KeyboardButton(text="📤 Экспорт"), KeyboardButton(text="🎖 Достижения")],
            [KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
    )


def category_kb() -> InlineKeyboardMarkup:
    cats = ["Здоровье", "Обучение", "Спорт", "Осознанность", "Работа", "Творчество", "Общее"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c, callback_data=f"cat:{c}")] for c in cats
    ])


def habits_list_kb(habits: list[Habit], action: str) -> InlineKeyboardMarkup:
    icons = {"done": "✅", "stats": "📊", "del": "🗑", "edit": "✏️", "qval": "🔢"}
    icon = icons.get(action, "▪️")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{icon} {h.name}", callback_data=f"{action}:{h.id}")]
        for h in habits
    ])


def mood_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"{n} {emoji}", callback_data=f"mood:{n}")
        for n, emoji in [(1, "😞"), (2, "😕"), (3, "😐"), (4, "🙂"), (5, "😄")]
    ]])


def export_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📄 CSV", callback_data="export:csv"),
        InlineKeyboardButton(text="📕 PDF", callback_data="export:pdf"),
    ]])


def settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏰ Время напоминаний", callback_data="set:reminder")],
        [InlineKeyboardButton(text="🎨 Стиль коуча", callback_data="set:motivation")],
        [InlineKeyboardButton(text="🗑 Удалить привычку", callback_data="set:delete")],
    ])


# ────── Онбординг (#1) ──────

def motivation_kb(prefix: str = "onb_mot") -> InlineKeyboardMarkup:
    """Кнопки выбора стиля. prefix позволяет использовать ту же клавиатуру в настройках."""
    styles = [
        MotivationStyle.SUPPORTIVE,
        MotivationStyle.DISCIPLINE,
        MotivationStyle.COMPETITION,
        MotivationStyle.GENTLE,
        MotivationStyle.PRODUCTIVITY,
    ]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=s.label, callback_data=f"{prefix}:{s.value}")]
        for s in styles
    ])


def focus_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=PriorityFocus.STREAK.label, callback_data="onb_focus:streak")],
        [InlineKeyboardButton(text=PriorityFocus.COMPLETION.label, callback_data="onb_focus:completion")],
    ])


# ────── Создание привычки: типы ──────

def habit_type_kb() -> InlineKeyboardMarkup:
    """Булевая vs количественная."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✓ Обычная (выполнил/нет)", callback_data="qtype:bool")],
        [InlineKeyboardButton(text="🔢 Количественная (литры, минуты, страницы…)", callback_data="qtype:quant")],
    ])


def habit_goal_kb() -> InlineKeyboardMarkup:
    """Постоянная привычка vs цель с дедлайном."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♾ Привычка (без срока)", callback_data="gtype:habit")],
        [InlineKeyboardButton(text="🎯 Цель (с дедлайном)", callback_data="gtype:goal")],
    ])


def goal_duration_kb() -> InlineKeyboardMarkup:
    """Быстрый выбор длительности цели."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="7 дней", callback_data="gdur:7"),
            InlineKeyboardButton(text="21 день", callback_data="gdur:21"),
        ],
        [
            InlineKeyboardButton(text="1 месяц", callback_data="gdur:30"),
            InlineKeyboardButton(text="3 месяца", callback_data="gdur:90"),
        ],
        [InlineKeyboardButton(text="✏️ Своё (дней)", callback_data="gdur:custom")],
    ])


# ────── Редактирование привычки ──────

def edit_field_kb() -> InlineKeyboardMarkup:
    """Какое поле менять у выбранной привычки."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Название", callback_data="ef:name")],
        [InlineKeyboardButton(text="📂 Категория", callback_data="ef:category")],
        [InlineKeyboardButton(text="🔢 Целевое значение", callback_data="ef:target")],
        [InlineKeyboardButton(text="📏 Единица измерения", callback_data="ef:unit")],
        [InlineKeyboardButton(text="🗓 Дедлайн цели", callback_data="ef:end_date")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="ef:cancel")],
    ])
