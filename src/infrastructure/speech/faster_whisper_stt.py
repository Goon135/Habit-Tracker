"""Локальное распознавание речи через faster-whisper.

Почему не openai whisper и не whisper.cpp напрямую: faster-whisper использует CTranslate2,
работает в 4-5x быстрее оригинального openai/whisper на CPU и не требует GPU.
Для бота с десятками юзеров — оптимально. Большой выигрыш по памяти.

Модель загружается один раз при создании объекта и держится в памяти.
"""
from __future__ import annotations

import asyncio
from functools import partial

from faster_whisper import WhisperModel


class FasterWhisperSTT:
    """
    model_size: 'tiny' | 'base' | 'small' | 'medium' | 'large-v3'.
    Для русского языка минимум 'small' — иначе много ошибок.
    На CPU 'small' даёт хорошее соотношение качество/скорость.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ru",
    ) -> None:
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._language = language

    async def transcribe(self, audio_path: str) -> str:
        # WhisperModel.transcribe — синхронный CPU-bound, выносим в thread.
        loop = asyncio.get_running_loop()
        segments, _info = await loop.run_in_executor(
            None,
            partial(
                self._model.transcribe,
                audio_path,
                language=self._language,
                beam_size=5,
                vad_filter=True,
            ),
        )
        # segments — генератор; материализуем в треде ниже, иначе будет блокировать event loop
        # при итерации (декодинг лениво).
        text_parts: list[str] = await loop.run_in_executor(
            None, lambda: [seg.text for seg in segments]
        )
        return "".join(text_parts).strip()
