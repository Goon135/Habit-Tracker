"""Прочие SQLAlchemy репозитории."""
from __future__ import annotations

from datetime import date

from sqlalchemy import and_, desc, select
from sqlalchemy.exc import IntegrityError

from src.domain.entities.achievement import Achievement
from src.domain.entities.coach_message import CoachMessage, CoachRole
from src.domain.entities.mood_entry import MoodEntry
from src.infrastructure.database.database import Database
from src.infrastructure.database.models.orm import (
    AchievementModel,
    CoachMessageModel,
    MoodEntryModel,
)


class SqlAlchemyAchievementRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def grant(self, achievement: Achievement) -> bool:
        async with self._db.session() as session:
            model = AchievementModel(
                user_id=achievement.user_id,
                code=achievement.code,
                title=achievement.title,
                description=achievement.description,
                earned_at=achievement.earned_at,
            )
            session.add(model)
            try:
                await session.commit()
                return True
            except IntegrityError:
                # уникальный ключ (user_id, code) уже занят
                await session.rollback()
                return False

    async def list_for_user(self, user_id: int) -> list[Achievement]:
        async with self._db.session() as session:
            stmt = (
                select(AchievementModel)
                .where(AchievementModel.user_id == user_id)
                .order_by(desc(AchievementModel.earned_at))
            )
            result = await session.execute(stmt)
            return [self._to_entity(m) for m in result.scalars().all()]

    async def list_codes_for_user(self, user_id: int) -> set[str]:
        async with self._db.session() as session:
            stmt = select(AchievementModel.code).where(AchievementModel.user_id == user_id)
            result = await session.execute(stmt)
            return {r[0] for r in result.all()}

    @staticmethod
    def _to_entity(m: AchievementModel) -> Achievement:
        return Achievement(
            id=m.id,
            user_id=m.user_id,
            code=m.code,
            title=m.title,
            description=m.description,
            earned_at=m.earned_at,
        )


class SqlAlchemyMoodRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, entry: MoodEntry) -> None:
        async with self._db.session() as session:
            existing = await session.execute(
                select(MoodEntryModel).where(
                    and_(
                        MoodEntryModel.user_id == entry.user_id,
                        MoodEntryModel.entry_date == entry.entry_date,
                    )
                )
            )
            model = existing.scalar_one_or_none()
            if model is None:
                session.add(MoodEntryModel(
                    user_id=entry.user_id,
                    entry_date=entry.entry_date,
                    score=entry.score,
                    note=entry.note,
                    created_at=entry.created_at,
                ))
            else:
                model.score = entry.score
                model.note = entry.note
            await session.commit()

    async def list_for_user(self, user_id: int, since: date) -> list[MoodEntry]:
        async with self._db.session() as session:
            stmt = (
                select(MoodEntryModel)
                .where(and_(MoodEntryModel.user_id == user_id, MoodEntryModel.entry_date >= since))
                .order_by(MoodEntryModel.entry_date)
            )
            result = await session.execute(stmt)
            return [
                MoodEntry(
                    id=m.id, user_id=m.user_id, entry_date=m.entry_date,
                    score=m.score, note=m.note, created_at=m.created_at,
                )
                for m in result.scalars().all()
            ]


class SqlAlchemyCoachMessageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, message: CoachMessage) -> None:
        async with self._db.session() as session:
            session.add(CoachMessageModel(
                user_id=message.user_id,
                role=message.role.value,
                content=message.content,
                created_at=message.created_at,
            ))
            await session.commit()

    async def list_recent(self, user_id: int, limit: int = 20) -> list[CoachMessage]:
        async with self._db.session() as session:
            stmt = (
                select(CoachMessageModel)
                .where(CoachMessageModel.user_id == user_id)
                .order_by(desc(CoachMessageModel.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            rows = list(result.scalars().all())
            rows.reverse()  # хронологический порядок: старые → новые
            return [
                CoachMessage(
                    id=m.id, user_id=m.user_id, role=CoachRole(m.role),
                    content=m.content, created_at=m.created_at,
                )
                for m in rows
            ]
