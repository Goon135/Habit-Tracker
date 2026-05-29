"""Достижение пользователя."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Achievement:
    user_id: int
    code: str  # стабильный код для дедупликации: "streak_7", "habits_5"
    title: str
    description: str
    earned_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
