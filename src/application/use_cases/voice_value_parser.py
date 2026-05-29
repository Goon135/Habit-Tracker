"""Парсер числа и единицы измерения из транскрипта голосового сообщения.

Используется в ProcessVoiceMessageUseCase: если пользователь говорит
«отметь воду 0.5 литра» / «выпил 500 мл воды» / «пробежал 5 км» — нужно
вытащить (value, unit) и нормализовать в единицу привычки.

Никаких внешних зависимостей: чистые функции, легко тестировать.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


# Нормализованные ключи единиц + все возможные написания (включая склонения,
# которые Whisper может выдать). Ключ — каноническая форма из ExtractedHabitDTO
# (см. дефолт: «литр», «страница», «минута», «шаг», «километр» — именительный
# единственного). Сравнение делаем по leading-substring основы слова, поэтому
# «литра», «литров», «литре» матчатся к «литр».
_UNIT_ALIASES: dict[str, tuple[str, ...]] = {
    "мл": ("мл", "миллилитр"),
    "л": ("л", "литр"),
    "г": ("г", "грамм"),
    "кг": ("кг", "килограмм"),
    "м": ("м", "метр"),
    "км": ("км", "километр"),
    "с": ("с", "сек", "секунд"),
    "мин": ("мин", "минут"),
    "ч": ("ч", "час"),
    "шаг": ("шаг",),
    "стр": ("стр", "страниц"),
    "раз": ("раз",),
    "ккал": ("ккал", "калори"),
}

# Коэффициенты приведения к базовой единице внутри группы.
# Группы изолированы: нельзя конвертировать литры в граммы.
_BASE_UNIT_PER_GROUP: dict[str, str] = {
    # объём
    "мл": "мл", "л": "мл",
    # масса
    "г": "г", "кг": "г",
    # длина
    "м": "м", "км": "м",
    # время
    "с": "с", "мин": "с", "ч": "с",
}
_TO_BASE: dict[str, float] = {
    "мл": 1.0, "л": 1000.0,
    "г": 1.0, "кг": 1000.0,
    "м": 1.0, "км": 1000.0,
    "с": 1.0, "мин": 60.0, "ч": 3600.0,
}


def _canonicalize_unit(token: str | None) -> str | None:
    """Привести произвольное написание единицы к канонической форме.

    Возвращает один из ключей _UNIT_ALIASES или None, если не распознали.
    """
    if not token:
        return None
    t = token.lower().strip(".,")
    for canon, aliases in _UNIT_ALIASES.items():
        for a in aliases:
            # Точное совпадение для коротких аббревиатур (мл, л, г, кг...).
            if len(a) <= 2 and t == a:
                return canon
            # Префиксное — для слов с возможными падежами («литра», «минут»).
            if len(a) > 2 and t.startswith(a):
                return canon
    return None


@dataclass(frozen=True)
class ParsedValue:
    """Результат парсинга числа из транскрипта.

    value — числовое значение, как сказал пользователь (до конвертации).
    unit — каноническая единица, которую он назвал (или None — единицы не было).
    """
    value: float
    unit: str | None


# Число: целое или дробное, с точкой или запятой, опционально со знаком.
# Дальше — опциональный пробел и токен единицы (слово из букв или короткая
# аббревиатура без пробела вроде «500мл»).
_NUMBER_RE = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>[а-яёa-z]+)?",
    re.IGNORECASE,
)


def parse_value(text: str) -> ParsedValue | None:
    """Извлечь первое число (опционально с единицей) из текста.

    Возвращает None, если ни одного числа нет.
    Если число есть, а единицы нет (или не распознали) — unit будет None.
    """
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    raw = m.group("value").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    unit = _canonicalize_unit(m.group("unit"))
    return ParsedValue(value=value, unit=unit)


def convert_to_habit_unit(
    parsed: ParsedValue,
    habit_unit: str | None,
) -> float:
    """Привести parsed.value к единице привычки.

    Логика:
    - Если у привычки нет unit — возвращаем число как есть (как при ручном
      вводе количества).
    - Если parsed.unit не распознан или не назван — считаем, что пользователь
      назвал число в единицах привычки (доверяем ему).
    - Если parsed.unit и habit_unit в одной группе (объём/масса/длина/время) —
      конвертируем через базовую единицу группы.
    - Если в разных группах (литры vs граммы) — возвращаем число как есть
      и предоставляем разруливать пользователю на следующей итерации.
      Альтернатива — кидать ошибку, но это сделает UX хрупким для опечаток
      Whisper'а («м» вместо «мин»).
    """
    if parsed.unit is None or habit_unit is None:
        return parsed.value

    parsed_canon = parsed.unit
    habit_canon = _canonicalize_unit(habit_unit)
    if habit_canon is None:
        # Привычка с нестандартной единицей («подход», «глава») — не конвертируем.
        return parsed.value

    if parsed_canon == habit_canon:
        return parsed.value

    parsed_group = _BASE_UNIT_PER_GROUP.get(parsed_canon)
    habit_group = _BASE_UNIT_PER_GROUP.get(habit_canon)
    if parsed_group is None or habit_group is None or parsed_group != habit_group:
        return parsed.value

    # Конвертация: parsed → база группы → habit.
    in_base = parsed.value * _TO_BASE[parsed_canon]
    return in_base / _TO_BASE[habit_canon]
