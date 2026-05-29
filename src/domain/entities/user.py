"""Пользователь — корневая сущность (aggregate root)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time

from src.domain.value_objects.coaching_mode import CoachingMode
from src.domain.value_objects.motivation_style import MotivationStyle
from src.domain.value_objects.priority_focus import PriorityFocus


@dataclass
class User:
    id: int  # Telegram user_id — естественный ключ
    username: str
    first_name: str
    points: int = 0
    level: int = 1
    reminder_time: time = field(default_factory=lambda: time(9, 0))
    coaching_mode: CoachingMode = CoachingMode.TEMPLATE
    registered_at: datetime = field(default_factory=datetime.utcnow)

    # Персонализация коуча (опросник онбординга, фича #1).
    motivation_style: MotivationStyle = MotivationStyle.NOT_SET
    priority_focus: PriorityFocus = PriorityFocus.NOT_SET
    onboarding_completed: bool = False

    # Long-term memory: периодически обновляемая LLM сводка о пользователе (фича #7).
    memory_summary: str = ""
    memory_updated_at: datetime | None = None

    # Recovery mode (#3) — режим анти-выгорания.
    # При recovery_until > today:
    # - targets количественных привычек снижаются на 30% при показе.
    # - напоминания подавляются.
    # - тон коуча смещается в GENTLE независимо от текущего стиля.
    recovery_until: date | None = None
    recovery_started_at: datetime | None = None
    last_insight_at: datetime | None = None  # для ratelimit /insights

    def add_points(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("points must be non-negative")
        self.points += amount
        self.level = 1 + self.points // 100

    def change_reminder_time(self, new_time: time) -> None:
        self.reminder_time = new_time

    def complete_onboarding(
        self,
        motivation_style: MotivationStyle,
        priority_focus: PriorityFocus,
    ) -> None:
        self.motivation_style = motivation_style
        self.priority_focus = priority_focus
        self.onboarding_completed = True

    def update_memory_summary(self, summary: str) -> None:
        self.memory_summary = summary
        self.memory_updated_at = datetime.utcnow()

    def is_in_recovery(self, today: date | None = None) -> bool:
        today = today or date.today()
        return self.recovery_until is not None and today <= self.recovery_until

    def enter_recovery(self, until: date) -> None:
        self.recovery_until = until
        self.recovery_started_at = datetime.utcnow()

    def exit_recovery(self) -> None:
        self.recovery_until = None
        self.recovery_started_at = None
