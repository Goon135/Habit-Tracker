"""Frequency: сериализация туда-обратно и валидация."""
import pytest

from src.domain.value_objects.frequency import Frequency


def test_daily_roundtrip():
    f = Frequency.daily()
    assert f.to_string() == "daily"
    assert Frequency.from_string("daily") == f


def test_weekly_n_roundtrip():
    f = Frequency.weekly(3)
    assert f.to_string() == "weekly_n:3"
    assert Frequency.from_string("weekly_n:3").times_per_week == 3


def test_weekdays_roundtrip_is_sorted():
    f = Frequency.on_weekdays({2, 0, 4})
    # Сортировка важна, чтобы строки сравнивались стабильно.
    assert f.to_string() == "weekdays:0,2,4"
    restored = Frequency.from_string("weekdays:0,2,4")
    assert restored.weekdays == frozenset({0, 2, 4})


def test_invalid_weekly_n_rejected():
    with pytest.raises(ValueError):
        Frequency.weekly(0)
    with pytest.raises(ValueError):
        Frequency.weekly(8)


def test_invalid_weekday_rejected():
    with pytest.raises(ValueError):
        Frequency.on_weekdays({7})
    with pytest.raises(ValueError):
        Frequency.on_weekdays(set())


def test_unknown_string_falls_back_to_daily():
    # Защита от данных из старых миграций / битых записей.
    assert Frequency.from_string("garbage").kind == "daily"
    assert Frequency.from_string("").kind == "daily"
