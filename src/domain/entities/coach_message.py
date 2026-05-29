"""Сообщение в диалоге с коучем (для контекста LLM)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CoachRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class CoachMessage:
    user_id: int
    role: CoachRole
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    id: int | None = None
