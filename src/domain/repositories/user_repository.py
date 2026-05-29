"""Интерфейсы репозиториев.

Используем typing.Protocol вместо ABC: структурная типизация без наследования,
infrastructure-классы не обязаны явно импортировать эти Protocol'ы.
Это идиоматично для Python и упрощает моки в тестах.
"""
from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

from src.domain.entities.user import User


@runtime_checkable
class UserRepository(Protocol):
    async def get(self, user_id: int) -> User | None: ...
    async def save(self, user: User) -> None: ...
    async def list_all_with_reminder(self) -> list[User]: ...
