"""Голосовые сообщения: download → Whisper → действие."""
from __future__ import annotations

import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from src.application.use_cases.process_voice import ProcessVoiceMessageUseCase
from src.presentation.handlers.states import CompleteQuantitative

logger = logging.getLogger(__name__)


def build_router(bot: Bot, process_voice: ProcessVoiceMessageUseCase) -> Router:
    router = Router(name="voice")

    @router.message(F.voice | F.audio)
    async def handle_voice(message: Message, state: FSMContext) -> None:
        file_obj = message.voice or message.audio
        await message.answer("🎙 Слушаю...")

        # Сохраняем во временный .ogg — Telegram отдаёт голосовые в OGG/OPUS.
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            tg_file = await bot.get_file(file_obj.file_id)
            await bot.download_file(tg_file.file_path, destination=tmp_path)

            result = await process_voice.execute(message.from_user.id, tmp_path)
        except Exception as exc:
            logger.exception("Voice processing failed: %s", exc)
            await message.answer("Что-то пошло не так с распознаванием. Попробуй ещё раз.")
            return
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if result.action == "unrecognized":
            await message.answer(
                f"🎙 Услышал: «{result.transcript}»\n\n"
                "Не понял, что ты хочешь сделать. Попробуй: «отметь медитацию» или "
                "«хочу читать перед сном»."
            )
            return

        if result.action == "needs_value":
            habit = result.affected_habits[0]
            unit = habit.unit or ""
            await state.set_state(CompleteQuantitative.waiting_value)
            await state.update_data(habit_id=result.pending_habit_id)
            await message.answer(
                f"🎙 Услышал: «{result.transcript}»\n\n"
                f"🔢 Сколько добавить к «{habit.name}»?\n"
                f"Цель в день: {habit.target_value:g} {unit}.\n"
                f"Введи число (можно дробное, разделитель — точка или запятая)."
            )
            return

        if result.action == "marked":
            names = ", ".join(h.name for h in result.affected_habits)
            await message.answer(
                f"🎙 Услышал: «{result.transcript}»\n\n✅ Отметил: {names}"
            )
            return

        # created
        lines = [f"🎙 Услышал: «{result.transcript}»\n", "✅ Создал привычки:"]
        for h in result.affected_habits:
            lines.append(f"  • {h.name} ({h.category.value})")
        await message.answer("\n".join(lines))

    return router
