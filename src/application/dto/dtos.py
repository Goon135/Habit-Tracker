"""DTO — простые data-классы для границы application/presentation.

Зачем отдельные DTO, если есть entities? Чтобы presentation не зависел от внутренних
сущностей напрямую и чтобы можно было собирать в DTO данные из нескольких сущностей
(например, прогресс = привычка + streak + лог за сегодня).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class HabitProgressDTO:
    habit_id: int
    name: str
    category: str
    streak: int
    completed_today: bool
    # Количественные привычки: накопленное значение и цель.
    current_value: float = 0.0
    target_value: float | None = None
    unit: str | None = None
    # Цели (#6).
    is_goal: bool = False
    end_date: date | None = None

    @property
    def is_quantitative(self) -> bool:
        return self.target_value is not None and self.target_value > 0

    @property
    def progress_ratio(self) -> float:
        if not self.is_quantitative:
            return 1.0 if self.completed_today else 0.0
        return min(self.current_value / self.target_value, 1.0)


@dataclass(frozen=True)
class CompletionResultDTO:
    streak: int
    points_earned: int
    total_points: int
    level: int
    level_title: str
    new_achievements: list[dict] = field(default_factory=list)
    # Поля для количественных привычек.
    current_value: float = 1.0
    target_value: float | None = None
    unit: str | None = None
    progress_ratio: float = 1.0
    completed: bool = True


@dataclass(frozen=True)
class ExtractedHabitDTO:
    """То, что LLM извлёк из произвольного текста пользователя."""
    name: str
    category: str
    frequency_kind: str  # "daily" | "weekly_n" | "weekdays"
    times_per_week: int | None = None
    weekdays: list[int] = field(default_factory=list)

    # Количественные привычки.
    # target_value — целевое числовое значение (например 20 страниц, 3 литра).
    # unit — единица измерения в именительном падеже единственного числа
    #        ("страница", "литр", "минута", "шаг", "километр"...).
    # Оба None для обычных булевых привычек.
    target_value: float | None = None
    unit: str | None = None

    # Привычка-цель с конечным сроком.
    # is_goal=True означает, что у привычки есть дедлайн.
    # duration_days — длительность в днях от сегодняшнего дня
    #   (1 неделя → 7, 1 месяц → 30). Преобразуется в end_date в use case.
    is_goal: bool = False
    duration_days: int | None = None


@dataclass(frozen=True)
class CoachReplyDTO:
    text: str
    mode: str  # "llm" | "template" — для логирования и презентации
