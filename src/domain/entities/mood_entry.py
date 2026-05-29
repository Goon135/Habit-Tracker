"""Отметка настроения за день (1..5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class MoodEntry:
    user_id: int
    entry_date: date
    score: int  # 1..5
    note: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.score <= 5:
            raise ValueError("mood score must be 1..5")
