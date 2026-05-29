"""ProcessVoiceMessageUseCase: маршрутизация транскрипта и поддержка
количественных привычек (создание + отметка с числом и без)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.use_cases.process_voice import (
    ProcessVoiceMessageUseCase,
    VoiceProcessingResult,
)
from src.domain.entities.habit import Habit
from src.domain.value_objects.category import Category


# ──────── Fakes ────────

@dataclass
class FakeSTT:
    """Возвращает заранее настроенный транскрипт, минуя реальный Whisper."""
    transcript: str = ""

    async def transcribe(self, audio_path: str) -> str:  # noqa: ARG002
        return self.transcript


@dataclass
class FakeHabitRepo:
    habits: dict[int, Habit] = field(default_factory=dict)
    _next_id: int = 1

    async def add(self, habit: Habit) -> Habit:
        habit.id = self._next_id
        self._next_id += 1
        self.habits[habit.id] = habit
        return habit

    async def get(self, habit_id: int):
        return self.habits.get(habit_id)

    async def list_for_user(self, user_id: int, active_only: bool = True):
        return [
            h for h in self.habits.values()
            if h.user_id == user_id and (not active_only or h.is_active)
        ]

    async def deactivate(self, habit_id: int, user_id: int) -> None:
        h = self.habits.get(habit_id)
        if h and h.user_id == user_id:
            h.is_active = False

    async def update(self, habit: Habit):
        self.habits[habit.id] = habit
        return habit

    async def list_expired_goals(self, today):  # noqa: ARG002
        return []


@dataclass
class FakeCompleteHabit:
    """Записывает вызовы execute — нам нужно проверить, что value прокидывается."""
    calls: list[tuple[int, int, float | None]] = field(default_factory=list)

    async def execute(self, user_id: int, habit_id: int, value: float | None = None):
        self.calls.append((user_id, habit_id, value))
        # Возвращаемое значение в process_voice не используется.
        return None


@dataclass
class FakeExtractHabits:
    """Заглушка ExtractHabitsFromTextUseCase: возвращает заранее заданные привычки."""
    will_create: list[Habit] = field(default_factory=list)
    last_text: str | None = None

    async def execute(self, user_id: int, free_text: str) -> list[Habit]:
        self.last_text = free_text
        # Эмулируем сохранение: ставим user_id и id.
        for i, h in enumerate(self.will_create, start=100):
            h.id = i
            h.user_id = user_id
        return list(self.will_create)


def _make_uc(
    transcript: str,
    habits: list[Habit] | None = None,
    will_create: list[Habit] | None = None,
):
    stt = FakeSTT(transcript=transcript)
    repo = FakeHabitRepo()
    for h in habits or []:
        # Сохраняем под собственным id, если он задан, иначе через add().
        if h.id is not None:
            repo.habits[h.id] = h
            repo._next_id = max(repo._next_id, h.id + 1)
        else:
            # синхронный вариант для удобства setup'а
            repo._next_id += 1
            h.id = repo._next_id - 1
            repo.habits[h.id] = h
    complete = FakeCompleteHabit()
    extract = FakeExtractHabits(will_create=will_create or [])
    uc = ProcessVoiceMessageUseCase(stt, repo, complete, extract)
    return uc, complete, extract


# ──────── Тесты ────────

@pytest.mark.asyncio
async def test_empty_transcript_is_unrecognized():
    uc, _, _ = _make_uc(transcript="")
    result = await uc.execute(user_id=1, audio_path="/tmp/x")
    assert result.action == "unrecognized"
    assert result.affected_habits == []


@pytest.mark.asyncio
async def test_boolean_habit_marked_without_value():
    """Булевая привычка: транскрипт «сделал медитация» → mark, value не передаётся.

    Имя в именительном падеже — текущий простой матчер ищет дословное вхождение
    (см. ограничение в _match_existing_habit). Падежи — отдельная задача.
    """
    medit = Habit(id=1, user_id=42, name="Медитация", category=Category.HEALTH)
    uc, complete, _ = _make_uc("Сделал медитация", habits=[medit])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "marked"
    assert result.affected_habits == [medit]
    assert complete.calls == [(42, 1, None)]


@pytest.mark.asyncio
async def test_quantitative_with_explicit_value():
    """«Сделал вода 0.5 литра» при unit=«литр» → value=0.5 передаётся в complete."""
    water = Habit(
        id=1, user_id=42, name="Вода", category=Category.HEALTH,
        target_value=3.0, unit="литр",
    )
    uc, complete, _ = _make_uc("Сделал вода 0.5 литра", habits=[water])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "marked"
    assert complete.calls == [(42, 1, 0.5)]


@pytest.mark.asyncio
async def test_quantitative_with_unit_conversion():
    """«500 мл вода» при unit=«литр» → конверсия в 0.5 л."""
    water = Habit(
        id=1, user_id=42, name="Вода",
        target_value=3.0, unit="литр",
    )
    uc, complete, _ = _make_uc("Отметь вода 500 мл", habits=[water])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "marked"
    assert complete.calls[0][2] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_quantitative_without_value_asks_for_input():
    """«Отметь вода» без числа → needs_value, complete НЕ вызывается."""
    water = Habit(
        id=7, user_id=42, name="Вода",
        target_value=3.0, unit="литр",
    )
    uc, complete, _ = _make_uc("Отметь вода", habits=[water])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "needs_value"
    assert result.pending_habit_id == 7
    assert result.affected_habits == [water]
    assert complete.calls == []  # complete не должен дёргаться без значения


@pytest.mark.asyncio
async def test_quantitative_minutes_to_hours():
    """«Сделал медитация 30 минут» при unit=«час» → 0.5."""
    medit = Habit(
        id=2, user_id=42, name="Медитация",
        target_value=1.0, unit="час",
    )
    uc, complete, _ = _make_uc("Сделал медитация 30 минут", habits=[medit])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "marked"
    assert complete.calls[0][2] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_no_trigger_word_falls_to_extraction():
    """«Хочу пить 3 литра воды в день» → extract, не mark."""
    new_water = Habit(
        id=None, user_id=0, name="Вода",
        target_value=3.0, unit="литр",
    )
    uc, complete, extract = _make_uc(
        "Хочу пить 3 литра воды в день",
        habits=[],
        will_create=[new_water],
    )

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "created"
    assert len(result.affected_habits) == 1
    assert result.affected_habits[0].target_value == 3.0
    assert complete.calls == []
    assert extract.last_text == "Хочу пить 3 литра воды в день"


@pytest.mark.asyncio
async def test_unknown_intent_falls_through_to_unrecognized():
    """Триггер-слова нет, экстрактор ничего не вернул → unrecognized."""
    uc, complete, _ = _make_uc("Сегодня хорошая погода", habits=[], will_create=[])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "unrecognized"
    assert complete.calls == []


@pytest.mark.asyncio
async def test_habit_match_is_case_insensitive():
    """Регистр транскрипта не должен мешать матчингу — Whisper иногда капсит."""
    medit = Habit(id=1, user_id=42, name="Медитация")
    uc, complete, _ = _make_uc("СДЕЛАЛ МЕДИТАЦИЯ", habits=[medit])

    result = await uc.execute(user_id=42, audio_path="/tmp/x")

    assert result.action == "marked"
    assert complete.calls == [(42, 1, None)]
