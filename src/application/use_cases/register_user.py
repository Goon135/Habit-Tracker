"""Use case: регистрация пользователя.

На регистрации детерминированно назначаем A/B-группу для эксперимента
(LLM-коуч vs шаблонные сообщения).
"""
from __future__ import annotations

from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.coaching_mode import CoachingMode


class RegisterUserUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: int, username: str, first_name: str) -> User:
        existing = await self._users.get(user_id)
        if existing is not None:
            return existing

        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            coaching_mode=CoachingMode.assign(user_id),
        )
        await self._users.save(user)
        return user
