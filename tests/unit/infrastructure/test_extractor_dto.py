"""Тесты для _to_dto OllamaHabitExtractor — нормализация полей quantitative/goal."""
from __future__ import annotations

import pytest

from src.infrastructure.llm.ollama_extractor import OllamaHabitExtractor


def test_target_value_and_unit_together_kept():
    """Количественная привычка: цель и единица заданы — оба сохраняются."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Читать", "category": "Обучение", "frequency_kind": "daily",
        "target_value": 20, "unit": "страница",
    })
    assert dto.target_value == 20.0
    assert dto.unit == "страница"


def test_target_value_without_unit_dropped():
    """LLM иногда забывает unit при target_value — должны очистить оба."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Бегать", "category": "Спорт", "frequency_kind": "daily",
        "target_value": 5,  # unit отсутствует
    })
    assert dto.target_value is None
    assert dto.unit is None


def test_unit_without_target_value_dropped():
    """Симметрично: unit без target_value — обнуляем."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Пить воду", "category": "Здоровье", "frequency_kind": "daily",
        "unit": "литр",
    })
    assert dto.target_value is None
    assert dto.unit is None


def test_negative_target_value_treated_as_missing():
    """Отрицательное target_value — это очевидная ошибка модели, обнуляем."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "X", "category": "Общее", "frequency_kind": "daily",
        "target_value": -3, "unit": "литр",
    })
    assert dto.target_value is None
    assert dto.unit is None


def test_unit_normalized_to_lowercase():
    """unit должен приводиться к нижнему регистру для единообразия."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Читать", "category": "Обучение", "frequency_kind": "daily",
        "target_value": 20, "unit": "Страница",
    })
    assert dto.unit == "страница"


def test_is_goal_with_duration_kept():
    """Цель с явной длительностью — оба поля сохраняются."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Читать", "category": "Обучение", "frequency_kind": "daily",
        "is_goal": True, "duration_days": 7,
    })
    assert dto.is_goal is True
    assert dto.duration_days == 7


def test_is_goal_without_duration_gets_default():
    """LLM говорит «цель», но забыл duration — подставляем 30 дней."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "X", "category": "Общее", "frequency_kind": "daily",
        "is_goal": True,
    })
    assert dto.is_goal is True
    assert dto.duration_days == 30


def test_duration_without_is_goal_dropped():
    """duration_days в одиночку без is_goal — обнуляем."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "X", "category": "Общее", "frequency_kind": "daily",
        "duration_days": 7,
    })
    assert dto.is_goal is False
    assert dto.duration_days is None


def test_quantitative_goal_combo():
    """Главный сценарий из задачи: '20 страниц в день на неделю'."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Читать", "category": "Обучение", "frequency_kind": "daily",
        "target_value": 20, "unit": "страница",
        "is_goal": True, "duration_days": 7,
    })
    assert dto.name == "Читать"
    assert dto.target_value == 20.0
    assert dto.unit == "страница"
    assert dto.is_goal is True
    assert dto.duration_days == 7


def test_plain_boolean_habit_no_extras():
    """Простая булевая привычка без числа и срока — все доп-поля None/False."""
    dto = OllamaHabitExtractor._to_dto({
        "name": "Медитировать", "category": "Осознанность", "frequency_kind": "daily",
    })
    assert dto.target_value is None
    assert dto.unit is None
    assert dto.is_goal is False
    assert dto.duration_days is None
