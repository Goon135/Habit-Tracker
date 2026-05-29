"""Извлечение привычек из произвольного текста через локальный Ollama.

Llama 3.1 8B поддерживает function calling нативно начиная с Ollama 0.4.
Передаём JSON-схему как dict, модель возвращает tool_calls в response.message.

Расширенный режим: извлекаем не только название/расписание, но и:
- target_value + unit для количественных привычек («20 страниц», «3 литра»);
- is_goal + duration_days для целей с конечным сроком («на неделю», «месяц»).

Маленьким моделям типа Llama 3.1 8B сложно различать измерительные единицы
и просто упоминания чисел, поэтому в системной инструкции даём 5 явных
примеров с разбором — это существенно поднимает точность.
"""
from __future__ import annotations

import json
import logging

from ollama import AsyncClient

from src.application.dto.dtos import ExtractedHabitDTO

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.1:8b"


# JSON-схема в формате OpenAI tools — Ollama принимает её один в один.
_TOOL = {
    "type": "function",
    "function": {
        "name": "save_habits",
        "description": (
            "Сохранить список привычек, извлечённых из сообщения пользователя. "
            "Если пользователь упомянул несколько привычек — верни их все. "
            "Если описал одну — верни список из одного элемента. "
            "Если в тексте нет привычек — верни habits=[]."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "habits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": (
                                    "Короткое название привычки в инфинитиве. "
                                    "Без количества и срока. "
                                    "Хорошо: 'Читать книги', 'Бегать по утрам'. "
                                    "Плохо: 'Читать 20 страниц на неделю'."
                                ),
                            },
                            "category": {
                                "type": "string",
                                "enum": [
                                    "Здоровье", "Обучение", "Спорт",
                                    "Осознанность", "Работа", "Творчество", "Общее",
                                ],
                                "description": "Категория привычки.",
                            },
                            "frequency_kind": {
                                "type": "string",
                                "enum": ["daily", "weekly_n", "weekdays"],
                                "description": (
                                    "Тип расписания. 'daily' — каждый день. "
                                    "'weekly_n' — N раз в неделю без фиксации дней. "
                                    "'weekdays' — конкретные дни недели."
                                ),
                            },
                            "times_per_week": {
                                "type": "integer",
                                "description": (
                                    "Для frequency_kind='weekly_n', сколько раз "
                                    "в неделю (1-7)."
                                ),
                            },
                            "weekdays": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": (
                                    "Для frequency_kind='weekdays': "
                                    "0=Пн, 1=Вт, ..., 6=Вс."
                                ),
                            },
                            # ===== Количественные привычки =====
                            "target_value": {
                                "type": "number",
                                "description": (
                                    "Целевое числовое значение в день. "
                                    "Заполняй ТОЛЬКО если в тексте явно указано "
                                    "число с единицей измерения: '20 страниц', "
                                    "'3 литра', '10000 шагов', '30 минут', "
                                    "'5 километров'. Если просто 'читать книги' "
                                    "без числа — НЕ ЗАПОЛНЯЙ."
                                ),
                            },
                            "unit": {
                                "type": "string",
                                "description": (
                                    "Единица измерения в именительном падеже "
                                    "единственного числа: 'страница', 'литр', "
                                    "'минута', 'шаг', 'километр', 'раз'. "
                                    "Заполняй ТОЛЬКО вместе с target_value."
                                ),
                            },
                            # ===== Цели с конечным сроком =====
                            "is_goal": {
                                "type": "boolean",
                                "description": (
                                    "true — если пользователь упомянул конечный "
                                    "срок: 'на неделю', 'месяц', 'до конца года', "
                                    "'в течение 30 дней'. "
                                    "false — если это постоянная привычка без срока."
                                ),
                            },
                            "duration_days": {
                                "type": "integer",
                                "description": (
                                    "Длительность цели в днях. Заполняй ТОЛЬКО "
                                    "если is_goal=true. "
                                    "Преобразуй: 'неделя' → 7, '2 недели' → 14, "
                                    "'месяц' → 30, '3 месяца' → 90, 'год' → 365. "
                                    "Если в тексте уже число дней — оставь как есть."
                                ),
                            },
                        },
                        "required": ["name", "category", "frequency_kind"],
                    },
                },
            },
            "required": ["habits"],
        },
    },
}


# Few-shot инструкция: для Llama 3.1 8B одних описаний параметров мало,
# нужны конкретные примеры. Они существенно поднимают точность извлечения
# тонких признаков (количество vs упоминание числа, цель vs привычка).
_SYSTEM = """Ты — парсер привычек. Получаешь произвольный текст и извлекаешь из него привычки. Всегда отвечай ТОЛЬКО вызовом инструмента save_habits, не пиши обычный текст.

ПРИМЕРЫ РАЗБОРА:

Текст: "хочу читать 20 страниц в день на протяжении недели"
Разбор: одна привычка, name='Читать', category='Обучение', frequency_kind='daily', target_value=20, unit='страница', is_goal=true, duration_days=7

Текст: "буду пить 3 литра воды каждый день"
Разбор: одна привычка, name='Пить воду', category='Здоровье', frequency_kind='daily', target_value=3, unit='литр', is_goal=false

Текст: "бегать по утрам и медитировать перед сном"
Разбор: ДВЕ привычки.
  1) name='Бегать по утрам', category='Спорт', frequency_kind='daily', без target_value, без is_goal
  2) name='Медитировать перед сном', category='Осознанность', frequency_kind='daily'

Текст: "ходить в спортзал три раза в неделю в течение месяца"
Разбор: name='Ходить в спортзал', category='Спорт', frequency_kind='weekly_n', times_per_week=3, is_goal=true, duration_days=30

Текст: "10000 шагов каждый день"
Разбор: name='Ходить', category='Здоровье', frequency_kind='daily', target_value=10000, unit='шаг', is_goal=false

ВАЖНЫЕ ПРАВИЛА:
- target_value заполняй ТОЛЬКО если в тексте есть число + единица измерения.
- Если число есть, но это число раз/частота (например "3 раза в неделю") — это идёт в times_per_week, НЕ в target_value.
- Если в тексте нет конечного срока — is_goal=false и duration_days НЕ заполняй.
- name должно быть БЕЗ количества и срока: "Читать", а не "Читать 20 страниц на неделю".
- "неделя"=7, "2 недели"=14, "месяц"=30, "3 месяца"=90, "полгода"=180, "год"=365."""


class OllamaHabitExtractor:
    def __init__(self, host: str = "http://localhost:11434", model: str = DEFAULT_MODEL) -> None:
        self._client = AsyncClient(host=host)
        self._model = model

    async def extract(self, free_text: str) -> list[ExtractedHabitDTO]:
        if not free_text.strip():
            return []

        try:
            response = await self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": free_text},
                ],
                tools=[_TOOL],
                options={"temperature": 0.0},  # детерминизм для извлечения
            )
        except Exception as exc:
            logger.warning("Ollama extraction error: %s", exc)
            return []

        tool_calls = response.message.tool_calls or []
        logger.info(
            "Ollama extract response: text=%r, tool_calls_count=%d",
            (response.message.content or "")[:200],
            len(tool_calls),
        )
        for i, tc in enumerate(tool_calls):
            logger.info(
                "  tool_call[%d]: name=%r, args=%r",
                i, tc.function.name, tc.function.arguments,
            )
        for tool_call in tool_calls:
            if tool_call.function.name != "save_habits":
                continue
            args = tool_call.function.arguments
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    logger.warning("Failed to parse tool_call args: %s", args[:200])
                    continue

            raw_habits = (args or {}).get("habits", []) or []

            # Защита от двойной сериализации (Llama 3.1 8B иногда так балуется).
            if isinstance(raw_habits, str):
                try:
                    raw_habits = json.loads(raw_habits)
                    logger.info("Unwrapped doubly-encoded habits string")
                except json.JSONDecodeError:
                    logger.warning(
                        "habits arg is a string but not valid JSON: %s",
                        raw_habits[:200],
                    )
                    raw_habits = []

            if not isinstance(raw_habits, list):
                logger.warning("habits is not a list after parsing: %r", type(raw_habits))
                return []

            return [self._to_dto(h) for h in raw_habits if isinstance(h, dict)]
        return []

    @staticmethod
    def _to_dto(raw: dict) -> ExtractedHabitDTO:
        # Количественные поля — нормализуем явные None и пустые строки.
        target_value = raw.get("target_value")
        unit = raw.get("unit")
        if target_value is not None:
            try:
                target_value = float(target_value)
                if target_value <= 0:
                    target_value = None
            except (TypeError, ValueError):
                target_value = None
        if unit is not None:
            unit = str(unit).strip().lower() or None
        # target_value и unit должны идти парой — если одно есть без другого, чистим оба.
        if (target_value is None) != (unit is None):
            target_value = None
            unit = None

        # Цель: is_goal и duration_days тоже идут парой.
        is_goal = bool(raw.get("is_goal", False))
        duration_days = raw.get("duration_days")
        if duration_days is not None:
            try:
                duration_days = int(duration_days)
                if duration_days <= 0:
                    duration_days = None
            except (TypeError, ValueError):
                duration_days = None
        if is_goal and duration_days is None:
            # Модель сказала «цель», но забыла указать длительность — по умолчанию месяц.
            duration_days = 30
        if not is_goal:
            duration_days = None

        return ExtractedHabitDTO(
            name=str(raw.get("name", "")).strip(),
            category=str(raw.get("category", "Общее")),
            frequency_kind=str(raw.get("frequency_kind", "daily")),
            times_per_week=raw.get("times_per_week"),
            weekdays=list(raw.get("weekdays") or []),
            target_value=target_value,
            unit=unit,
            is_goal=is_goal,
            duration_days=duration_days,
        )
