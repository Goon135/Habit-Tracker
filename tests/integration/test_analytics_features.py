"""Интеграционные тесты для recovery mode и insights (фичи #1, #2, #3)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from src.application.use_cases.burnout import (
    AssessBurnoutRiskUseCase,
    ToggleRecoveryModeUseCase,
)
from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.application.use_cases.create_habit import CreateHabitUseCase
from src.application.use_cases.generate_insights import GenerateInsightsUseCase
from src.application.use_cases.get_today_progress import GetTodayProgressUseCase
from src.domain.entities.user import User
from src.infrastructure.database.repositories.habit_repo import (
    SqlAlchemyHabitLogRepository,
    SqlAlchemyHabitRepository,
)
from src.infrastructure.database.repositories.other_repos import (
    SqlAlchemyAchievementRepository,
    SqlAlchemyMoodRepository,
)
from src.infrastructure.database.repositories.user_repo import SqlAlchemyUserRepository


async def _make_user(db, uid: int = 1) -> User:
    users = SqlAlchemyUserRepository(db)
    user = User(id=uid, username="u", first_name="A")
    await users.save(user)
    return user


# ─────────── Recovery mode (#3) ───────────

@pytest.mark.asyncio
async def test_toggle_recovery_enter_and_exit(db):
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    toggle = ToggleRecoveryModeUseCase(users)

    # Начально не в recovery.
    status_before = await toggle.status(1)
    assert not status_before.is_active

    # Входим на 3 дня.
    enter_result = await toggle.enter(1, days=3)
    assert enter_result.is_active
    assert enter_result.days_left == 3
    assert enter_result.until == date.today() + timedelta(days=3)

    # Перечитываем — recovery_until сохранён.
    reloaded = await users.get(1)
    assert reloaded.is_in_recovery()

    # Выходим.
    await toggle.exit(1)
    reloaded = await users.get(1)
    assert not reloaded.is_in_recovery()


@pytest.mark.asyncio
async def test_get_today_progress_lowers_target_in_recovery(db):
    """В recovery mode target_value снижается на 30% при показе."""
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    create = CreateHabitUseCase(habits)
    toggle = ToggleRecoveryModeUseCase(users)
    progress = GetTodayProgressUseCase(logs, users)

    await create.execute(user_id=1, name="Вода", target_value=10.0, unit="л")

    # Без recovery — target = 10.
    result_before = await progress.execute(1)
    assert len(result_before) == 1
    assert result_before[0].target_value == 10.0

    # В recovery — target снижается до 7.
    await toggle.enter(1, days=3)
    result_after = await progress.execute(1)
    assert result_after[0].target_value == 7.0  # 10 * 0.7

    # Выходим — target возвращается.
    await toggle.exit(1)
    result_back = await progress.execute(1)
    assert result_back[0].target_value == 10.0


@pytest.mark.asyncio
async def test_recovery_does_not_change_db_target(db):
    """Снижение target в recovery — только при показе, в БД исходное значение."""
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    create = CreateHabitUseCase(habits)
    toggle = ToggleRecoveryModeUseCase(users)

    h = await create.execute(user_id=1, name="X", target_value=10.0)
    await toggle.enter(1, days=3)

    # В БД target_value не должен измениться.
    reloaded = await habits.get(h.id)
    assert reloaded.target_value == 10.0


# ─────────── Burnout assessment (#2) ───────────

@pytest.mark.asyncio
async def test_burnout_assessment_low_for_new_user(db):
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    moods = SqlAlchemyMoodRepository(db)
    assess = AssessBurnoutRiskUseCase(habits, logs, moods)

    result = await assess.execute(1)
    assert result.level == "low"
    assert result.score == 0


@pytest.mark.asyncio
async def test_burnout_assessment_high_for_inactive_user(db):
    """Пользователь с привычкой, но без выполнений 5 дней → HIGH/MEDIUM."""
    await _make_user(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    moods = SqlAlchemyMoodRepository(db)
    create = CreateHabitUseCase(habits)
    assess = AssessBurnoutRiskUseCase(habits, logs, moods)

    await create.execute(user_id=1, name="Бег")
    # Никаких выполнений, никакого настроения — за 30 дней пустота.
    # Это даст inactive_days и low completion → как минимум MEDIUM.
    result = await assess.execute(1)
    assert result.level in ("medium", "high")
    assert result.inactive_days >= 3


# ─────────── Insights (#1) ───────────

@pytest.mark.asyncio
async def test_insights_returns_none_without_data(db):
    """Без логов инсайт не считаем — возвращаем None."""
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    moods = SqlAlchemyMoodRepository(db)
    create = CreateHabitUseCase(habits)
    insights = GenerateInsightsUseCase(users, habits, logs, moods, formatter=None)

    # Привычка есть, но логов нет.
    await create.execute(user_id=1, name="X")
    result = await insights.execute(1)
    assert result is None


@pytest.mark.asyncio
async def test_insights_works_without_formatter_fallback(db):
    """Без LLM-форматтера используется template-fallback и формирует summary_text."""
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    moods = SqlAlchemyMoodRepository(db)
    achievements = SqlAlchemyAchievementRepository(db)
    create = CreateHabitUseCase(habits)
    complete = CompleteHabitUseCase(users, habits, logs, achievements)
    insights = GenerateInsightsUseCase(users, habits, logs, moods, formatter=None)

    h = await create.execute(user_id=1, name="Медитация")
    # Несколько выполнений в разные дни.
    for i in range(5):
        await complete.execute(1, h.id, today=date.today() - timedelta(days=i))

    result = await insights.execute(1)
    assert result is not None
    assert not result.formatted_by_llm
    assert result.summary_text  # текст собран фоллбэком
    assert result.total_completions >= 5
    assert result.heatmap_ascii  # heatmap всегда есть


@pytest.mark.asyncio
async def test_insights_updates_last_insight_at(db):
    """После генерации инсайта user.last_insight_at должен обновиться."""
    await _make_user(db)
    users = SqlAlchemyUserRepository(db)
    habits = SqlAlchemyHabitRepository(db)
    logs = SqlAlchemyHabitLogRepository(db)
    moods = SqlAlchemyMoodRepository(db)
    achievements = SqlAlchemyAchievementRepository(db)
    create = CreateHabitUseCase(habits)
    complete = CompleteHabitUseCase(users, habits, logs, achievements)
    insights = GenerateInsightsUseCase(users, habits, logs, moods, formatter=None)

    h = await create.execute(user_id=1, name="X")
    for i in range(3):
        await complete.execute(1, h.id, today=date.today() - timedelta(days=i))

    before = await users.get(1)
    assert before.last_insight_at is None

    await insights.execute(1)
    after = await users.get(1)
    assert after.last_insight_at is not None
    assert isinstance(after.last_insight_at, datetime)
