"""Use case: обработать голосовое сообщение.

Поток: voice file path → SpeechToText.transcribe → текст → решение:
- Если текст похож на "отметь X" / "сделал X" — найти привычку, отметить.
  Для количественных привычек дополнительно парсим число из транскрипта;
  если числа нет — возвращаем action="needs_value", чтобы хендлер
  спросил его текстом (симметрично UX кнопок).
- Иначе — пытаемся извлечь как новую привычку.

Здесь мы оставляем простую эвристику: ключевые слова. Более умную диспетчеризацию
можно потом отдать в отдельный LLM-роутер, но для MVP это перебор.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.application.interfaces.ai_services import SpeechToText
from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.application.use_cases.extract_habits import ExtractHabitsFromTextUseCase
from src.application.use_cases.voice_value_parser import (
    convert_to_habit_unit,
    parse_value,
)
from src.domain.entities.habit import Habit
from src.domain.repositories.habit_repository import HabitRepository


_MARK_DONE_TRIGGERS = ("отметь", "сделал", "сделала", "выполнил", "выполнила", "готово")


@dataclass(frozen=True)
class VoiceProcessingResult:
    transcript: str
    # "marked" | "created" | "unrecognized" | "needs_value"
    # "needs_value" — нашли количественную привычку, но числа в транскрипте
    # не было. Хендлер должен попросить число текстом.
    action: str
    affected_habits: list[Habit] = field(default_factory=list)
    # habit_id привычки, которая ждёт ввода числа. Заполняется только при
    # action == "needs_value".
    pending_habit_id: int | None = None


class ProcessVoiceMessageUseCase:
    def __init__(
        self,
        stt: SpeechToText,
        habits: HabitRepository,
        complete_habit: CompleteHabitUseCase,
        extract_habits: ExtractHabitsFromTextUseCase,
    ) -> None:
        self._stt = stt
        self._habits = habits
        self._complete = complete_habit
        self._extract = extract_habits

    async def execute(self, user_id: int, audio_path: str) -> VoiceProcessingResult:
        transcript = (await self._stt.transcribe(audio_path)).strip()
        if not transcript:
            return VoiceProcessingResult(transcript="", action="unrecognized")

        lower = transcript.lower()
        if any(t in lower for t in _MARK_DONE_TRIGGERS):
            matched = await self._match_existing_habit(user_id, lower)
            if matched is not None:
                # Количественные требуют значения — либо извлечём из транскрипта,
                # либо попросим ввести вручную.
                if matched.is_quantitative:
                    parsed = parse_value(lower)
                    if parsed is None:
                        return VoiceProcessingResult(
                            transcript=transcript,
                            action="needs_value",
                            affected_habits=[matched],
                            pending_habit_id=matched.id,
                        )
                    value = convert_to_habit_unit(parsed, matched.unit)
                    await self._complete.execute(user_id, matched.id, value=value)
                else:
                    await self._complete.execute(user_id, matched.id)
                return VoiceProcessingResult(
                    transcript=transcript, action="marked", affected_habits=[matched]
                )

        # Иначе — пробуем создать.
        created = await self._extract.execute(user_id, transcript)
        if created:
            return VoiceProcessingResult(
                transcript=transcript, action="created", affected_habits=created
            )
        return VoiceProcessingResult(transcript=transcript, action="unrecognized")

    async def _match_existing_habit(self, user_id: int, lower_text: str) -> Habit | None:
        habits = await self._habits.list_for_user(user_id, active_only=True)
        # Берём первую привычку, чьё название встречается в тексте.
        # Очень простой матчинг, но для голосового UX этого достаточно.
        for h in habits:
            if h.name.lower() in lower_text:
                return h
        return None
