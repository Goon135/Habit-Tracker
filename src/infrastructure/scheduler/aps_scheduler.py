"""APScheduler — все фоновые задачи бота.

Джобы:
- reminders_tick (каждую минуту): отправка ежедневных напоминаний.
- archive_goals_tick (00:05 UTC): архивация просроченных целей (#6).
- burnout_check_tick (09:00 UTC ежедневно): проверка риска burnout
  и предложение recovery при HIGH (#3).
- weekly_insights_tick (воскресенье 19:00 UTC): рассылка персональной
  аналитики всем пользователям с достаточной историей (#1).

Все колбэки — async методы класса, замыкающие use cases через self.
Это требует MemoryJobStore (нельзя пиклить); персистентность не нужна,
потому что джобы пересоздаются при старте, а смысловое состояние —
в БД через users.last_insight_at и пр.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.application.interfaces.external import Notifier
from src.application.use_cases.archive_expired_goals import ArchiveExpiredGoalsUseCase
from src.application.use_cases.burnout import CheckBurnoutAndProposeRecoveryUseCase
from src.application.use_cases.generate_insights import GenerateInsightsUseCase
from src.application.use_cases.send_reminders import SendRemindersUseCase
from src.domain.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(
        self,
        send_reminders: SendRemindersUseCase,
        archive_goals: ArchiveExpiredGoalsUseCase,
        check_burnout: CheckBurnoutAndProposeRecoveryUseCase,
        generate_insights: GenerateInsightsUseCase,
        users: UserRepository,
        notifier: Notifier,
    ) -> None:
        self._send_reminders = send_reminders
        self._archive_goals = archive_goals
        self._check_burnout = check_burnout
        self._generate_insights = generate_insights
        self._users = users
        self._notifier = notifier
        self._scheduler = AsyncIOScheduler(timezone="UTC")

    def start(self) -> None:
        self._scheduler.add_job(
            self._reminders_tick,
            CronTrigger(minute="*"),
            id="reminders_tick",
            replace_existing=True,
        )
        self._scheduler.add_job(
            self._archive_goals_tick,
            CronTrigger(hour=0, minute=5),
            id="archive_goals_tick",
            replace_existing=True,
        )
        # Проверка burnout — раз в день в 9:00 UTC, когда большинство уже проснулись.
        self._scheduler.add_job(
            self._burnout_check_tick,
            CronTrigger(hour=9, minute=0),
            id="burnout_check_tick",
            replace_existing=True,
        )
        # Еженедельная рассылка инсайтов — воскресенье 19:00 UTC.
        self._scheduler.add_job(
            self._weekly_insights_tick,
            CronTrigger(day_of_week="sun", hour=19, minute=0),
            id="weekly_insights_tick",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info("APScheduler started")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)

    async def _reminders_tick(self) -> None:
        try:
            sent = await self._send_reminders.execute()
            if sent:
                logger.info("Sent %d reminders", sent)
        except Exception as exc:
            logger.exception("Reminder tick failed: %s", exc)

    async def _archive_goals_tick(self) -> None:
        try:
            archived = await self._archive_goals.execute()
            if archived:
                logger.info("Archived %d expired goals", len(archived))
        except Exception as exc:
            logger.exception("Goal archive tick failed: %s", exc)

    async def _burnout_check_tick(self) -> None:
        try:
            offered = await self._check_burnout.execute()
            if offered:
                logger.info("Offered recovery to %d users", offered)
        except Exception as exc:
            logger.exception("Burnout check tick failed: %s", exc)

    async def _weekly_insights_tick(self) -> None:
        """Считает и рассылает инсайт всем пользователям с достаточной историей."""
        try:
            users = await self._users.list_all_with_reminder()
        except Exception as exc:
            logger.exception("Weekly insights — could not list users: %s", exc)
            return

        sent = 0
        for user in users:
            try:
                insight = await self._generate_insights.execute(user.id)
            except Exception as exc:
                logger.warning("insight failed for user %s: %r", user.id, exc)
                continue
            if insight is None:
                continue  # данных мало
            text = (
                f"📊 Еженедельная сводка\n\n{insight.summary_text}\n\n"
                f"Подробнее — /insights"
            )
            try:
                await self._notifier.send_text(user.id, text)
                sent += 1
            except Exception:
                continue
        if sent:
            logger.info("Weekly insights sent to %d users", sent)
