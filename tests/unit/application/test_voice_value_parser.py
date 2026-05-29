"""Парсер числа+единицы и конвертация в единицу привычки."""
from __future__ import annotations

import pytest

from src.application.use_cases.voice_value_parser import (
    ParsedValue,
    convert_to_habit_unit,
    parse_value,
)


class TestParseValue:
    def test_no_number_returns_none(self):
        assert parse_value("отметь воду") is None

    def test_integer(self):
        p = parse_value("выпил 2 литра воды")
        assert p == ParsedValue(value=2.0, unit="л")

    def test_decimal_with_dot(self):
        p = parse_value("выпил 0.5 литра")
        assert p == ParsedValue(value=0.5, unit="л")

    def test_decimal_with_comma(self):
        p = parse_value("отметь воду 1,5 литра")
        assert p == ParsedValue(value=1.5, unit="л")

    def test_no_space_between_number_and_unit(self):
        p = parse_value("выпил 500мл")
        assert p == ParsedValue(value=500.0, unit="мл")

    def test_unit_inflected_form(self):
        # Whisper часто выдаёт падежи — «литров», «минут», «страниц».
        assert parse_value("прочитал 30 страниц").unit == "стр"
        assert parse_value("медитировал 15 минут").unit == "мин"
        assert parse_value("пробежал 5 километров").unit == "км"

    def test_no_unit(self):
        # «отметь книгу 30» — число без явной единицы.
        p = parse_value("отметь книгу 30")
        assert p == ParsedValue(value=30.0, unit=None)

    def test_zero_and_negative_rejected(self):
        # 0 и отрицательные не имеют смысла как «добавить к прогрессу».
        assert parse_value("выпил 0 литров") is None

    def test_first_number_wins(self):
        # Если в фразе два числа — берём первое.
        p = parse_value("отметь привычку 2, выпил 500мл")
        assert p.value == 2.0

    def test_unit_aliases(self):
        # Короткие аббревиатуры без слова.
        assert parse_value("100 г").unit == "г"
        assert parse_value("2 кг").unit == "кг"
        assert parse_value("30 мин").unit == "мин"


class TestConvertToHabitUnit:
    def test_same_unit_passes_through(self):
        assert convert_to_habit_unit(ParsedValue(2.0, "л"), "литр") == 2.0

    def test_ml_to_l(self):
        # 500 мл при цели в литрах → 0.5
        assert convert_to_habit_unit(ParsedValue(500.0, "мл"), "литр") == 0.5

    def test_l_to_ml(self):
        # 1.5 литра при цели в мл → 1500
        assert convert_to_habit_unit(ParsedValue(1.5, "л"), "мл") == 1500.0

    def test_g_kg(self):
        assert convert_to_habit_unit(ParsedValue(500.0, "г"), "кг") == 0.5
        assert convert_to_habit_unit(ParsedValue(2.0, "кг"), "г") == 2000.0

    def test_m_km(self):
        assert convert_to_habit_unit(ParsedValue(500.0, "м"), "километр") == 0.5
        assert convert_to_habit_unit(ParsedValue(5.0, "км"), "м") == 5000.0

    def test_min_h(self):
        assert convert_to_habit_unit(ParsedValue(90.0, "мин"), "час") == 1.5
        assert convert_to_habit_unit(ParsedValue(2.0, "ч"), "минута") == 120.0

    def test_no_parsed_unit_assumes_habit_unit(self):
        # Пользователь сказал «отметь книгу 30» — доверяем, что 30 в единицах привычки.
        assert convert_to_habit_unit(ParsedValue(30.0, None), "страница") == 30.0

    def test_no_habit_unit_passes_through(self):
        # У привычки нет единицы (вырожденный кейс) — берём число как есть.
        assert convert_to_habit_unit(ParsedValue(5.0, "л"), None) == 5.0

    def test_cross_group_falls_back(self):
        # Литры → граммы — разные физические величины. Не конвертируем,
        # отдаём число как сказали (пусть пользователь увидит несоответствие).
        assert convert_to_habit_unit(ParsedValue(2.0, "л"), "грамм") == 2.0

    def test_unknown_habit_unit_passes_through(self):
        # Привычка с нестандартной единицей («подход», «глава»). Числа,
        # сказанные с конкретной единицей, тоже не конвертируем.
        assert convert_to_habit_unit(ParsedValue(3.0, "л"), "подход") == 3.0
