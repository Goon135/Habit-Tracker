"""Тесты под новые фичи: количественные привычки, цели, редактирование, онбординг."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from src.application.use_cases.archive_expired_goals import ArchiveExpiredGoalsUseCase
from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.application.use_cases.create_habit import CreateHabitUseCase
from src.application.use_cases.onboarding import (
    CompleteOnboardingUseCase,
    UpdateMotivationStyleUseCase,
)
from src.application.use_cases.update_habit import (
    UNSET,
    UpdateHabitFields,
    UpdateHabitUseCase,
)
from src.domain.entities.user import User
from src.domain.value_objects.category import Category
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus
from src.infrastructure.database.repositories.habit_repo import (
    SqlAlchemyHabitLogRepository,
    SqlAlchemyHabitRepository,
)
from src.infrastructure.database.repositories.other_repos import (
    SqlAlchemyAchievementRepository,
)
from src.infrastructure.database.repositories.user_repo import SqlAlchemyUserRepository


# ─────────── Helpers ───────────

async def _make_user(db, uid: int = 1) -> User:
    users = SqlAlchemyUserRepository(db)
    user = User(id=uid, username="u", first_name="A")
    await users.save(user)
    return user


# ─────────── Количественные привычки (#2) ───────────

@pytest.mark.asyncio
async def test_create_quantitative_habit(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    uc = CreateHabitUseCase(habits)

    h = await uc.execute(
        user_id=1, name="Вода", category=Category.HEALTH,
        target_value=3.0, unit="л",
    )

    assert h.is_quantitative
    assert h.target_value == 3.0
    assert h.unit == "л"
    assert not h.is_goal


@pytest.mark.asyncio
async def test_quantitative_negative_target_rejected(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    uc = CreateHabitUseCase(habits)

    with pytest.raises(ValueError):
        await uc.execute(user_id=1, name="X", target_value=-1.0)


@pytest.mark.asyncio
async def test_complete_quantitative_accumulates_value(db):
    """Несколько отметок за день суммируются, completed=True достигается при cumul >= target."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    users = SqlAlchemyUserRepository(db)
    achievements = SqlAlchemyAchievementRepository(db)

    create = CreateHabitUseCase(habits)
    complete = CompleteHabitUseCase(users, habits, logs, achievements)

    h = await create.execute(user_id=1, name="Вода", target_value=3.0, unit="л")

    # Первая отметка — 1.0, ещё не выполнено.
    r1 = await complete.execute(1, h.id, value=1.0)
    assert r1.current_value == 1.0
    assert not r1.completed
    assert r1.points_earned == 0  # очки только при выполнении

    # Вторая — добавляем ещё 1.5, итого 2.5, всё ещё не выполнено.
    r2 = await complete.execute(1, h.id, value=1.5)
    assert r2.current_value == 2.5
    assert not r2.completed

    # Третья — добавляем 1.0, итого 3.5, теперь выполнено.
    r3 = await complete.execute(1, h.id, value=1.0)
    assert r3.current_value == 3.5
    assert r3.completed
    assert r3.points_earned > 0


@pytest.mark.asyncio
async def test_boolean_habit_completes_in_one_shot(db):
    """Для булевой привычки value игнорируется, completed=True сразу."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    users = SqlAlchemyUserRepository(db)
    achievements = SqlAlchemyAchievementRepository(db)

    create = CreateHabitUseCase(habits)
    complete = CompleteHabitUseCase(users, habits, logs, achievements)

    h = await create.execute(user_id=1, name="Медитация")
    result = await complete.execute(1, h.id)
    assert result.completed
    assert result.target_value is None
    assert result.points_earned > 0


# ─────────── Редактирование (#5) ───────────

@pytest.mark.asyncio
async def test_update_habit_name_only(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    create = CreateHabitUseCase(habits)
    update = UpdateHabitUseCase(habits)

    h = await create.execute(user_id=1, name="Старое имя", category=Category.SPORT)

    updated = await update.execute(1, h.id, UpdateHabitFields(name="Новое имя"))
    assert updated is not None
    assert updated.name == "Новое имя"
    # Категория не должна была измениться.
    assert updated.category == Category.SPORT


@pytest.mark.asyncio
async def test_update_habit_target_to_zero_removes_quantitative(db):
    """target_value=None через UpdateHabitFields превращает количественную в булевую."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    create = CreateHabitUseCase(habits)
    update = UpdateHabitUseCase(habits)

    h = await create.execute(user_id=1, name="Вода", target_value=3.0, unit="л")
    assert h.is_quantitative

    updated = await update.execute(
        1, h.id, UpdateHabitFields(target_value=None, unit=None),
    )
    assert updated is not None
    assert not updated.is_quantitative
    assert updated.target_value is None
    assert updated.unit is None


@pytest.mark.asyncio
async def test_update_habit_wrong_owner_returns_none(db):
    await _make_user(db, uid=1)
    await _make_user(db, uid=2)
    habits = SqlAlchemyHabitRepository(db)
    create = CreateHabitUseCase(habits)
    update = UpdateHabitUseCase(habits)

    h = await create.execute(user_id=1, name="X")
    # Другой пользователь не может обновлять.
    result = await update.execute(2, h.id, UpdateHabitFields(name="hacked"))
    assert result is None


@pytest.mark.asyncio
async def test_update_habit_unset_means_no_change(db):
    """Поля со значением UNSET не должны затирать существующие значения."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    create = CreateHabitUseCase(habits)
    update = UpdateHabitUseCase(habits)

    h = await create.execute(
        user_id=1, name="X", category=Category.SPORT,
        target_value=5.0, unit="км",
    )

    # Меняем только имя — остальное должно остаться.
    updated = await update.execute(1, h.id, UpdateHabitFields(name="Y"))
    assert updated.name == "Y"
    assert updated.category == Category.SPORT
    assert updated.target_value == 5.0
    assert updated.unit == "км"


# ─────────── Цели и архивация (#6) ───────────

@pytest.mark.asyncio
async def test_goal_requires_end_date(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    uc = CreateHabitUseCase(habits)

    with pytest.raises(ValueError):
        await uc.execute(user_id=1, name="Цель", is_goal=True, end_date=None)


@pytest.mark.asyncio
async def test_goal_with_past_end_date_rejected(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    uc = CreateHabitUseCase(habits)

    with pytest.raises(ValueError):
        await uc.execute(
            user_id=1, name="Цель",
            is_goal=True, end_date=date.today() - timedelta(days=1),
        )


@pytest.mark.asyncio
async def test_archive_expired_goals_deactivates(db):
    """Истёкшая цель должна стать is_active=False."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    create = CreateHabitUseCase(habits)
    archive = ArchiveExpiredGoalsUseCase(habits, logs, notifier=None)

    # Создаём цель с end_date в будущем, потом руками двигаем end_date в прошлое.
    goal = await create.execute(
        user_id=1, name="Бег 10 дней",
        is_goal=True, end_date=date.today() + timedelta(days=1),
    )
    # Симулируем «прошедший срок» — двигаем end_date в прошлое через update.
    update = UpdateHabitUseCase(habits)
    await update.execute(
        1, goal.id,
        UpdateHabitFields(end_date=date.today() + timedelta(days=1)),
    )
    # Запускаем архивацию «как будто завтра» — цель просрочена.
    archived = await archive.execute(today=date.today() + timedelta(days=2))
    assert len(archived) == 1
    assert archived[0].name == "Бег 10 дней"
    # Проверяем, что в БД is_active=False.
    refreshed = await habits.get(goal.id)
    assert not refreshed.is_active


@pytest.mark.asyncio
async def test_archive_skips_non_expired_goals(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    create = CreateHabitUseCase(habits)
    archive = ArchiveExpiredGoalsUseCase(habits, logs, notifier=None)

    # Активная цель с большим запасом.
    await create.execute(
        user_id=1, name="Долгая цель",
        is_goal=True, end_date=date.today() + timedelta(days=30),
    )
    # Обычная активная привычка (не цель) — тоже не трогаем.
    await create.execute(user_id=1, name="Постоянная")

    archived = await archive.execute()
    assert archived == []


# ─────────── Онбординг (#1) ───────────

@pytest.mark.asyncio
async def test_complete_onboarding_sets_flags(db):
    user = await _make_user(db)
    assert not user.onboarding_completed
    assert user.motivation_style == MotivationStyle.NOT_SET

    users = SqlAlchemyUserRepository(db)
    uc = CompleteOnboardingUseCase(users)

    updated = await uc.execute(
        user_id=1,
        motivation_style=MotivationStyle.DISCIPLINE,
        priority_focus=PriorityFocus.STREAK,
    )
    assert updated.onboarding_completed
    assert updated.motivation_style == MotivationStyle.DISCIPLINE
    assert updated.priority_focus == PriorityFocus.STREAK

    # Перезагружаем из БД — проверяем персистентность.
    reloaded = await users.get(1)
    assert reloaded.onboarding_completed
    assert reloaded.motivation_style == MotivationStyle.DISCIPLINE


@pytest.mark.asyncio
async def test_update_motivation_style_only(db):
    """Смена стиля из настроек не должна затрагивать focus и onboarding_completed."""
    user = await _make_user(db)
    users = SqlAlchemyUserRepository(db)

    onboarding = CompleteOnboardingUseCase(users)
    await onboarding.execute(1, MotivationStyle.SUPPORTIVE, PriorityFocus.COMPLETION)

    change = UpdateMotivationStyleUseCase(users)
    updated = await change.execute(1, MotivationStyle.PRODUCTIVITY)

    assert updated.motivation_style == MotivationStyle.PRODUCTIVITY
    assert updated.priority_focus == PriorityFocus.COMPLETION
    assert updated.onboarding_completed


# ─────────── Motivation prompt ───────────

def test_each_motivation_style_has_instruction():
    for style in MotivationStyle:
        if style == MotivationStyle.NOT_SET:
            assert style.prompt_instruction == ""
        else:
            assert style.prompt_instruction
            assert style.label
