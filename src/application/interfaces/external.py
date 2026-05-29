"""Интерфейсы для экспорта отчётов и отправки уведомлений."""
from __future__ import annotations

from io import BytesIO
from typing import Protocol, runtime_checkable


@runtime_checkable
class ReportExporter(Protocol):
    async def export_csv(self, user_id: int, days: int) -> BytesIO: ...
    async def export_pdf(self, user_id: int, days: int) -> BytesIO: ...


@runtime_checkable
class Notifier(Protocol):
    """Отправка сообщений пользователю.

    В domain/application мы не знаем о Telegram. Реализация в infrastructure
    оборачивает aiogram Bot.
    """

    async def send_text(self, user_id: int, text: str) -> None: ...
