"""Экспорт отчётов в CSV/PDF."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from src.application.interfaces.external import ReportExporter
from src.presentation.keyboards.keyboards import export_kb


def build_router(exporter: ReportExporter) -> Router:
    router = Router(name="export")

    @router.message(F.text == "📤 Экспорт")
    @router.message(Command("export"))
    async def export_menu(message: Message) -> None:
        await message.answer(
            "📤 Какой формат отчёта за последние 30 дней?",
            reply_markup=export_kb(),
        )

    @router.callback_query(F.data == "export:csv")
    async def export_csv(callback: CallbackQuery) -> None:
        await callback.answer("Готовлю CSV...")
        buf = await exporter.export_csv(callback.from_user.id, days=30)
        await callback.message.answer_document(
            BufferedInputFile(buf.read(), filename="habits_report.csv"),
            caption="📄 CSV-отчёт за 30 дней",
        )

    @router.callback_query(F.data == "export:pdf")
    async def export_pdf(callback: CallbackQuery) -> None:
        await callback.answer("Готовлю PDF...")
        buf = await exporter.export_pdf(callback.from_user.id, days=30)
        await callback.message.answer_document(
            BufferedInputFile(buf.read(), filename="habits_report.pdf"),
            caption="📕 PDF-отчёт за 30 дней",
        )

    return router
