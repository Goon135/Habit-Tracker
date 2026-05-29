"""Use case: завершить онбординг — сохранить выбор стиля и фокуса.

Вызывается в конце мини-опроса после /start (фича #1).
"""
from __future__ import annotations

from src.domain.entities.user import User
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus


class CompleteOnboardingUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(
        self,
        user_id: int,
        motivation_style: MotivationStyle,
        priority_focus: PriorityFocus,
    ) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        user.complete_onboarding(motivation_style, priority_focus)
        await self._users.save(user)
        return user


class UpdateMotivationStyleUseCase:
    """Менять стиль вне онбординга — из настроек."""

    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: int, style: MotivationStyle) -> User:
        user = await self._users.get(user_id)
        if user is None:
            raise RuntimeError(f"user {user_id} not found")
        user.motivation_style = style
        await self._users.save(user)
        return user
