"""Use case: разослать напоминания пользователям, у которых сейчас время напоминания.

Вызывается планировщиком (APScheduler) каждую минуту.
"""
from __future__ import annotations

from datetime import date, datetime

from src.application.interfaces.external import Notifier
from src.application.use_cases.get_today_progress import GetTodayProgressUseCase
from src.domain.repositories.user_repository import UserRepository


class SendRemindersUseCase:
    def __init__(
        self,
        users: UserRepository,
        today_progress: GetTodayProgressUseCase,
        notifier: Notifier,
    ) -> None:
        self._users = users
        self._today_progress = today_progress
        self._notifier = notifier

    async def execute(self, now: datetime | None = None) -> int:
        """Возвращает количество отправленных напоминаний."""
        now = now or datetime.now()
        current_hm = now.strftime("%H:%M")

        users = await self._users.list_all_with_reminder()
        sent = 0
        for user in users:
            if user.reminder_time.strftime("%H:%M") != current_hm:
                continue
            # Recovery mode: не дёргаем напоминаниями (#3).
            if user.is_in_recovery(now.date()):
                continue
            progress = await self._today_progress.execute(user.id, today=now.date())
            pending = [p for p in progress if not p.completed_today]
            if not pending:
                continue

            lines = "\n".join(f"  ⬜ {p.name}" for p in pending)
            text = (
                f"⏰ Напоминание!\n\n"
                f"Невыполненных привычек: {len(pending)}\n\n"
                f"{lines}\n\n"
                f"Открой бота и отметь выполнение!"
            )
            try:
                await self._notifier.send_text(user.id, text)
                sent += 1
            except Exception:
                # Не хотим, чтобы один заблокировавший бота юзер ронял рассылку.
                continue
        return sent
