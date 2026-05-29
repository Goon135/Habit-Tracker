"""SQLAlchemy реализация HabitRepository и HabitLogRepository."""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.domain.entities.habit import Habit
from src.domain.entities.habit_log import HabitLog
from src.domain.value_objects.category import Category
from src.domain.value_objects.frequency import Frequency
from src.infrastructure.database.database import Database
from src.infrastructure.database.models.orm import HabitLogModel, HabitModel


class SqlAlchemyHabitRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, habit: Habit) -> Habit:
        async with self._db.session() as session:
            model = HabitModel(
                user_id=habit.user_id,
                name=habit.name,
                category=habit.category.value,
                frequency=habit.frequency.to_string(),
                is_active=habit.is_active,
                created_at=habit.created_at,
                target_value=habit.target_value,
                unit=habit.unit,
                is_goal=habit.is_goal,
                end_date=habit.end_date,
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return self._to_entity(model)

    async def get(self, habit_id: int) -> Habit | None:
        async with self._db.session() as session:
            model = await session.get(HabitModel, habit_id)
            return self._to_entity(model) if model else None

    async def list_for_user(self, user_id: int, active_only: bool = True) -> list[Habit]:
        async with self._db.session() as session:
            stmt = select(HabitModel).where(HabitModel.user_id == user_id)
            if active_only:
                stmt = stmt.where(HabitModel.is_active.is_(True))
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def deactivate(self, habit_id: int, user_id: int) -> None:
        async with self._db.session() as session:
            model = await session.get(HabitModel, habit_id)
            if model is not None and model.user_id == user_id:
                model.is_active = False
                await session.commit()

    async def update(self, habit: Habit) -> Habit | None:
        """Полное обновление полей привычки. Возвращает None, если не найдено
        или не принадлежит пользователю (проверяется по habit.user_id)."""
        if habit.id is None:
            raise ValueError("habit.id is required for update")
        async with self._db.session() as session:
            model = await session.get(HabitModel, habit.id)
            if model is None or model.user_id != habit.user_id:
                return None
            model.name = habit.name
            model.category = habit.category.value
            model.frequency = habit.frequency.to_string()
            model.is_active = habit.is_active
            model.target_value = habit.target_value
            model.unit = habit.unit
            model.is_goal = habit.is_goal
            model.end_date = habit.end_date
            await session.commit()
            await session.refresh(model)
            return self._to_entity(model)

    async def list_expired_goals(self, today: date) -> list[Habit]:
        """Активные цели с истёкшим end_date — для авто-архивации в scheduler."""
        async with self._db.session() as session:
            stmt = select(HabitModel).where(
                and_(
                    HabitModel.is_active.is_(True),
                    HabitModel.is_goal.is_(True),
                    HabitModel.end_date.is_not(None),
                    HabitModel.end_date < today,
                )
            )
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    @staticmethod
    def _to_entity(m: HabitModel) -> Habit:
        return Habit(
            id=m.id,
            user_id=m.user_id,
            name=m.name,
            category=Category.from_string(m.category),
            frequency=Frequency.from_string(m.frequency),
            is_active=m.is_active,
            created_at=m.created_at,
            target_value=m.target_value,
            unit=m.unit,
            is_goal=m.is_goal,
            end_date=m.end_date,
        )


class SqlAlchemyHabitLogRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def upsert(self, log: HabitLog) -> None:
        """ON CONFLICT (habit_id, log_date) DO UPDATE.

        В SQLAlchemy 2.0 для async нет общего портативного upsert через core ORM,
        поэтому используем диалект-специфичные insert'ы. Поддерживаем Postgres + SQLite,
        этого хватает (тесты на SQLite, прод на Postgres).
        """
        async with self._db.session() as session:
            dialect = session.bind.dialect.name
            values = dict(
                habit_id=log.habit_id,
                user_id=log.user_id,
                log_date=log.log_date,
                completed=log.completed,
                value=log.value,
                logged_at=log.logged_at,
            )
            if dialect == "postgresql":
                stmt = pg_insert(HabitLogModel).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["habit_id", "log_date"],
                    set_={"completed": stmt.excluded.completed, "value": stmt.excluded.value},
                )
            else:
                stmt = sqlite_insert(HabitLogModel).values(**values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["habit_id", "log_date"],
                    set_={"completed": stmt.excluded.completed, "value": stmt.excluded.value},
                )
            await session.execute(stmt)
            await session.commit()

    async def get_for_date(self, habit_id: int, log_date: date) -> HabitLog | None:
        """Вернуть лог конкретной привычки за конкретный день (или None)."""
        async with self._db.session() as session:
            stmt = select(HabitLogModel).where(
                and_(HabitLogModel.habit_id == habit_id, HabitLogModel.log_date == log_date)
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            return self._to_entity(model) if model else None

    async def list_for_habit(self, habit_id: int, since: date) -> list[HabitLog]:
        async with self._db.session() as session:
            stmt = (
                select(HabitLogModel)
                .where(and_(HabitLogModel.habit_id == habit_id, HabitLogModel.log_date >= since))
                .order_by(HabitLogModel.log_date)
            )
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def list_completed_dates(self, habit_id: int) -> list[date]:
        async with self._db.session() as session:
            stmt = (
                select(HabitLogModel.log_date)
                .where(and_(HabitLogModel.habit_id == habit_id, HabitLogModel.completed.is_(True)))
            )
            result = await session.execute(stmt)
            return [r[0] for r in result.all()]

    async def list_for_user_in_range(
        self, user_id: int, since: date, until: date
    ) -> list[HabitLog]:
        """Все логи пользователя в диапазоне [since, until], для аналитики."""
        async with self._db.session() as session:
            stmt = (
                select(HabitLogModel)
                .where(and_(
                    HabitLogModel.user_id == user_id,
                    HabitLogModel.log_date >= since,
                    HabitLogModel.log_date <= until,
                ))
                .order_by(HabitLogModel.log_date)
            )
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def today_status(
        self, user_id: int, today: date
    ) -> list[tuple[Habit, bool]]:
        """Список активных привычек пользователя с пометкой, выполнена ли каждая сегодня."""
        async with self._db.session() as session:
            habits_stmt = select(HabitModel).where(
                and_(HabitModel.user_id == user_id, HabitModel.is_active.is_(True))
            )
            habits = (await session.execute(habits_stmt)).scalars().all()
            if not habits:
                return []
            habit_ids = [h.id for h in habits]

            logs_stmt = select(HabitLogModel).where(
                and_(
                    HabitLogModel.habit_id.in_(habit_ids),
                    HabitLogModel.log_date == today,
                )
            )
            logs = (await session.execute(logs_stmt)).scalars().all()
            completed_map: dict[int, bool] = {log.habit_id: log.completed for log in logs}

            return [
                (SqlAlchemyHabitRepository._to_entity(h), completed_map.get(h.id, False))
                for h in habits
            ]

    @staticmethod
    def _to_entity(m: HabitLogModel) -> HabitLog:
        return HabitLog(
            id=m.id,
            habit_id=m.habit_id,
            user_id=m.user_id,
            log_date=m.log_date,
            completed=m.completed,
            value=m.value,
            logged_at=m.logged_at,
        )
