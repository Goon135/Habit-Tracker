"""Режим коучинга для A/B-эксперимента (исследовательская часть диплома).

Каждый пользователь при регистрации детерминированно попадает в одну из групп
на основе хэша от user_id. Это даёт стабильное разделение без хранения отдельной
таблицы назначений.

ВАЖНО: используем hashlib, а не builtin hash(). hash() в CPython рандомизируется
при старте интерпретатора (PYTHONHASHSEED), и юзер мог бы менять группу при
каждом рестарте — это сломало бы валидность эксперимента.
"""
from __future__ import annotations

import hashlib
from enum import Enum


class CoachingMode(str, Enum):
    TEMPLATE = "template"  # Контрольная группа: шаблонные сообщения.
    LLM = "llm"            # Экспериментальная: LLM-генерация.

    @classmethod
    def assign(cls, user_id: int, salt: str = "habitbot_v1") -> "CoachingMode":
        """Детерминированное A/B-разделение по user_id.

        Salt позволяет ре-рандомизировать эксперимент в будущей версии,
        не теряя совместимости со старыми данными.
        """
        digest = hashlib.md5(f"{salt}:{user_id}".encode()).digest()
        bucket = digest[0] % 2
        return cls.LLM if bucket == 0 else cls.TEMPLATE
