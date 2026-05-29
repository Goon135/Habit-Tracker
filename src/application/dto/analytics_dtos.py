"""DTO для аналитики и burnout-детектора (#1, #2, #3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class InsightDTO:
    """То, что пользователь увидит после /insights или в еженедельной рассылке."""
    period_days: int
    completion_rate: float           # 0..1
    total_completions: int
    best_weekday_name: str | None
    worst_weekday_name: str | None
    best_weekday_rate: float | None
    mood_delta_pct: float | None     # отрицательное — после плохого настроения хуже
    has_significant_mood_correlation: bool
    heatmap_ascii: str
    declining_trend: bool
    # Текстовая часть: либо собрано правилами, либо отформатировано LLM.
    summary_text: str
    formatted_by_llm: bool


@dataclass(frozen=True)
class BurnoutAssessmentDTO:
    level: str                       # "low" | "medium" | "high"
    level_emoji: str
    level_label: str                 # русское «низкий/средний/высокий»
    score: int                       # 0..100
    factors: list[str] = field(default_factory=list)
    inactive_days: int = 0
    completion_rate_7d: float = 0.0


@dataclass(frozen=True)
class RecoveryStateDTO:
    """Текущее состояние recovery mode пользователя."""
    is_active: bool
    until: date | None = None
    days_left: int = 0
    started_at: date | None = None
