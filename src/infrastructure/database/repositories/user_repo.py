"""SQLAlchemy реализация UserRepository."""
from __future__ import annotations

from sqlalchemy import select

from src.domain.entities.user import User
from src.domain.value_objects.coaching_mode import CoachingMode
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus
from src.infrastructure.database.database import Database
from src.infrastructure.database.models.orm import UserModel


class SqlAlchemyUserRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, user_id: int) -> User | None:
        async with self._db.session() as session:
            model = await session.get(UserModel, user_id)
            return self._to_entity(model) if model else None

    async def save(self, user: User) -> None:
        async with self._db.session() as session:
            existing = await session.get(UserModel, user.id)
            if existing is None:
                session.add(self._to_model(user))
            else:
                existing.username = user.username
                existing.first_name = user.first_name
                existing.points = user.points
                existing.level = user.level
                existing.reminder_time = user.reminder_time
                existing.coaching_mode = user.coaching_mode.value
                existing.motivation_style = user.motivation_style.value
                existing.priority_focus = user.priority_focus.value
                existing.onboarding_completed = user.onboarding_completed
                existing.memory_summary = user.memory_summary
                existing.memory_updated_at = user.memory_updated_at
                existing.recovery_until = user.recovery_until
                existing.recovery_started_at = user.recovery_started_at
                existing.last_insight_at = user.last_insight_at
            await session.commit()

    async def list_all_with_reminder(self) -> list[User]:
        async with self._db.session() as session:
            stmt = select(UserModel)
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    @staticmethod
    def _to_entity(m: UserModel) -> User:
        return User(
            id=m.id,
            username=m.username,
            first_name=m.first_name,
            points=m.points,
            level=m.level,
            reminder_time=m.reminder_time,
            coaching_mode=CoachingMode(m.coaching_mode),
            registered_at=m.registered_at,
            motivation_style=MotivationStyle(m.motivation_style),
            priority_focus=PriorityFocus(m.priority_focus),
            onboarding_completed=m.onboarding_completed,
            memory_summary=m.memory_summary or "",
            memory_updated_at=m.memory_updated_at,
            recovery_until=m.recovery_until,
            recovery_started_at=m.recovery_started_at,
            last_insight_at=m.last_insight_at,
        )

    @staticmethod
    def _to_model(u: User) -> UserModel:
        return UserModel(
            id=u.id,
            username=u.username,
            first_name=u.first_name,
            points=u.points,
            level=u.level,
            reminder_time=u.reminder_time,
            coaching_mode=u.coaching_mode.value,
            registered_at=u.registered_at,
            motivation_style=u.motivation_style.value,
            priority_focus=u.priority_focus.value,
            onboarding_completed=u.onboarding_completed,
            memory_summary=u.memory_summary,
            memory_updated_at=u.memory_updated_at,
            recovery_until=u.recovery_until,
            recovery_started_at=u.recovery_started_at,
            last_insight_at=u.last_insight_at,
        )
