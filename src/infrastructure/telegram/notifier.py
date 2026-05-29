"""Реализация Notifier поверх aiogram Bot.

Позволяет use case'ам слать сообщения, не зная о Telegram.
"""
from __future__ import annotations

from aiogram import Bot


class TelegramNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(self, user_id: int, text: str) -> None:
        await self._bot.send_message(user_id, text)
