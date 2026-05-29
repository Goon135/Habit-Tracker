"""Уровень риска burnout / срыва — результат работы BurnoutDetector.

Используется в двух местах:
- Аналитика #2: общий риск ухода/срыва пользователя.
- Recovery mode #3: при HIGH автоматически предлагаем recovery.
"""
from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

    @property
    def emoji(self) -> str:
        return {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🔴",
        }[self]

    @property
    def label(self) -> str:
        return {
            RiskLevel.LOW: "низкий",
            RiskLevel.MEDIUM: "средний",
            RiskLevel.HIGH: "высокий",
        }[self]
