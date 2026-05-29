"""FSM-состояния для пошаговых сценариев."""
from aiogram.fsm.state import State, StatesGroup


class AddHabit(StatesGroup):
    waiting_name = State()
    waiting_category = State()
    waiting_quantitative_choice = State()  # количественная или булевая?
    waiting_target_value = State()         # для количественных: целевое число
    waiting_unit = State()                 # для количественных: единица измерения
    waiting_goal_choice = State()          # обычная или цель?
    waiting_goal_duration = State()        # для цели: длительность (дн/нед/мес)


class SetReminder(StatesGroup):
    waiting_time = State()


class CoachChat(StatesGroup):
    chatting = State()


class MoodFlow(StatesGroup):
    waiting_note = State()


class Onboarding(StatesGroup):
    """Опрос после /start: стиль мотивации и приоритет."""
    waiting_motivation = State()
    waiting_focus = State()


class EditHabit(StatesGroup):
    choosing_habit = State()    # выбор какую привычку править
    choosing_field = State()    # выбор какое поле
    waiting_new_name = State()
    waiting_new_category = State()
    waiting_new_target = State()
    waiting_new_unit = State()
    waiting_new_end_date = State()


class CompleteQuantitative(StatesGroup):
    """Для количественной привычки: ввод фактического значения."""
    waiting_value = State()
