"""Расписание привычки.

Поддерживаем три варианта:
- DAILY: каждый день.
- WEEKLY_N: N раз в неделю, без фиксации дней.
- WEEKDAYS: набор дней недели (0=Пн … 6=Вс).

Сериализация в строку нужна для хранения в БД одним полем — не плодим лишних
таблиц для расписания, пока требования не выросли.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Frequency:
    kind: str  # "daily" | "weekly_n" | "weekdays"
    times_per_week: int | None = None
    weekdays: frozenset[int] = field(default_factory=frozenset)

    @classmethod
    def daily(cls) -> "Frequency":
        return cls(kind="daily")

    @classmethod
    def weekly(cls, times: int) -> "Frequency":
        if not 1 <= times <= 7:
            raise ValueError("times_per_week must be between 1 and 7")
        return cls(kind="weekly_n", times_per_week=times)

    @classmethod
    def on_weekdays(cls, days: set[int]) -> "Frequency":
        if not days or any(d < 0 or d > 6 for d in days):
            raise ValueError("weekdays must be a non-empty subset of 0..6")
        return cls(kind="weekdays", weekdays=frozenset(days))

    def to_string(self) -> str:
        if self.kind == "daily":
            return "daily"
        if self.kind == "weekly_n":
            return f"weekly_n:{self.times_per_week}"
        if self.kind == "weekdays":
            return "weekdays:" + ",".join(str(d) for d in sorted(self.weekdays))
        raise ValueError(f"Unknown kind: {self.kind}")

    @classmethod
    def from_string(cls, raw: str) -> "Frequency":
        if not raw or raw == "daily":
            return cls.daily()
        if raw.startswith("weekly_n:"):
            return cls.weekly(int(raw.split(":")[1]))
        if raw.startswith("weekdays:"):
            days = {int(x) for x in raw.split(":")[1].split(",") if x}
            return cls.on_weekdays(days)
        return cls.daily()
