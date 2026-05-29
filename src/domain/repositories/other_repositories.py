"""Прочие репозитории."""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from src.domain.entities.achievement import Achievement
from src.domain.entities.coach_message import CoachMessage
from src.domain.entities.mood_entry import MoodEntry


@runtime_checkable
class AchievementRepository(Protocol):
    async def grant(self, achievement: Achievement) -> bool:
        """Возвращает True если выдано, False если уже было."""
        ...
    async def list_for_user(self, user_id: int) -> list[Achievement]: ...
    async def list_codes_for_user(self, user_id: int) -> set[str]: ...


@runtime_checkable
class MoodRepository(Protocol):
    async def add(self, entry: MoodEntry) -> None: ...
    async def list_for_user(self, user_id: int, since: date) -> list[MoodEntry]: ...


@runtime_checkable
class CoachMessageRepository(Protocol):
    async def add(self, message: CoachMessage) -> None: ...
    async def list_recent(self, user_id: int, limit: int = 20) -> list[CoachMessage]: ...
