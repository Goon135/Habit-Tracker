"""Integration-тест ExtractHabitsFromTextUseCase.

Проверяем, что DTO от экстрактора (в т.ч. количественные и цели)
корректно превращается в Habit и сохраняется. Реальный LLM не дёргаем —
подменяем FakeExtractor, возвращающим заранее заданные DTO.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.application.dto.dtos import ExtractedHabitDTO
from src.application.use_cases.extract_habits import ExtractHabitsFromTextUseCase
from src.domain.entities.user import User
from src.infrastructure.database.repositories.habit_repo import (
    SqlAlchemyHabitRepository,
)
from src.infrastructure.database.repositories.user_repo import SqlAlchemyUserRepository


class FakeExtractor:
    """Минимальный заменитель HabitExtractor для тестов."""
    def __init__(self, dtos: list[ExtractedHabitDTO]) -> None:
        self._dtos = dtos

    async def extract(self, text: str) -> list[ExtractedHabitDTO]:
        return self._dtos


async def _seed_user(db) -> None:
    users = SqlAlchemyUserRepository(db)
    await users.save(User(id=1, username="u", first_name="A"))


# ───────── главный сценарий из задачи ─────────

@pytest.mark.asyncio
async def test_quantitative_goal_creates_habit_with_target_and_end_date(db):
    """«Читать 20 страниц в день на неделю» → количественная цель."""
    await _seed_user(db)
    habits = SqlAlchemyHabitRepository(db)
    extractor = FakeExtractor([
        ExtractedHabitDTO(
            name="Читать",
            category="Обучение",
            frequency_kind="daily",
            target_value=20.0,
            unit="страница",
            is_goal=True,
            duration_days=7,
        ),
    ])
    use_case = ExtractHabitsFromTextUseCase(habits, extractor)

    created = await use_case.execute(user_id=1, free_text="ignored, fake extractor")
    assert len(created) == 1

    saved = created[0]
    assert saved.name == "Читать"
    assert saved.target_value == 20.0
    assert saved.unit == "страница"
    assert saved.is_quantitative
    assert saved.is_goal is True
    assert saved.end_date == date.today() + timedelta(days=7)


@pytest.mark.asyncio
async def test_plain_quantitative_no_goal(db):
    """«3 литра воды каждый день» — количественная, но без срока."""
    await _seed_user(db)
    habits = SqlAlchemyHabitRepository(db)
    extractor = FakeExtractor([
        ExtractedHabitDTO(
            name="Пить воду",
            category="Здоровье",
            frequency_kind="daily",
            target_value=3.0,
            unit="литр",
            is_goal=False,
        ),
    ])

    created = await ExtractHabitsFromTextUseCase(habits, extractor).execute(1, "x")
    assert len(created) == 1
    h = created[0]
    assert h.is_quantitative
    assert h.is_goal is False
    assert h.end_date is None


@pytest.mark.asyncio
async def test_boolean_habit_remains_simple(db):
    """«медитировать перед сном» — обычная булевая привычка."""
    await _seed_user(db)
    habits = SqlAlchemyHabitRepository(db)
    extractor = FakeExtractor([
        ExtractedHabitDTO(
            name="Медитировать", category="Осознанность", frequency_kind="daily",
        ),
    ])

    [h] = await ExtractHabitsFromTextUseCase(habits, extractor).execute(1, "x")
    assert h.is_quantitative is False
    assert h.target_value is None
    assert h.unit is None
    assert h.is_goal is False


@pytest.mark.asyncio
async def test_is_goal_flag_without_duration_falls_back(db):
    """Если по какой-то причине is_goal=True, а duration_days=None после нормализации,
    привычка должна остаться без срока, не падать с ошибкой."""
    await _seed_user(db)
    habits = SqlAlchemyHabitRepository(db)
    # ExtractedHabitDTO с is_goal=True но duration_days=None (минуя нормализатор экстрактора).
    extractor = FakeExtractor([
        ExtractedHabitDTO(
            name="Х", category="Общее", frequency_kind="daily",
            is_goal=True, duration_days=None,
        ),
    ])

    [h] = await ExtractHabitsFromTextUseCase(habits, extractor).execute(1, "x")
    # Защита use_case'а: без duration_days цель «деградирует» в обычную привычку.
    assert h.is_goal is False
    assert h.end_date is None
