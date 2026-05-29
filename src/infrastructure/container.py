"""Контейнер зависимостей.

Здесь — единственная точка, где знают про конкретные классы инфраструктуры
и собирают их в use cases. Нигде в presentation/application/domain эти конкретные
классы не упоминаются.

Решение: ручная сборка без di-фреймворков (dependency-injector, punq, и т.д.).
Для проекта такого размера это проще и понятнее, не требует магии для тестов.
"""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot

from src.application.interfaces.ai_services import (
    HabitExtractor,
    LLMCoach,
    LLMInsightFormatter,
    LLMSummarizer,
    SpeechToText,
)
from src.application.interfaces.external import Notifier, ReportExporter
from src.application.use_cases.archive_expired_goals import ArchiveExpiredGoalsUseCase
from src.application.use_cases.burnout import (
    AssessBurnoutRiskUseCase,
    CheckBurnoutAndProposeRecoveryUseCase,
    ToggleRecoveryModeUseCase,
)
from src.application.use_cases.coach_reply import CoachReplyUseCase
from src.application.use_cases.complete_habit import CompleteHabitUseCase
from src.application.use_cases.create_habit import CreateHabitUseCase
from src.application.use_cases.extract_habits import ExtractHabitsFromTextUseCase
from src.application.use_cases.generate_insights import GenerateInsightsUseCase
from src.application.use_cases.get_today_progress import GetTodayProgressUseCase
from src.application.use_cases.mood import LogMoodUseCase, MoodCorrelationUseCase
from src.application.use_cases.onboarding import (
    CompleteOnboardingUseCase,
    UpdateMotivationStyleUseCase,
)
from src.application.use_cases.process_voice import ProcessVoiceMessageUseCase
from src.application.use_cases.register_user import RegisterUserUseCase
from src.application.use_cases.send_reminders import SendRemindersUseCase
from src.application.use_cases.update_habit import UpdateHabitUseCase
from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import (
    AchievementRepository,
    CoachMessageRepository,
    MoodRepository,
)
from src.domain.repositories.user_repository import UserRepository
from src.infrastructure.config import Settings
from src.infrastructure.database.database import Database
from src.infrastructure.database.repositories.habit_repo import (
    SqlAlchemyHabitLogRepository,
    SqlAlchemyHabitRepository,
)
from src.infrastructure.database.repositories.other_repos import (
    SqlAlchemyAchievementRepository,
    SqlAlchemyCoachMessageRepository,
    SqlAlchemyMoodRepository,
)
from src.infrastructure.database.repositories.user_repo import SqlAlchemyUserRepository
from src.infrastructure.export.report_exporter import ReportExporterImpl
from src.infrastructure.llm.graceful_coach import GracefulCoach
from src.infrastructure.llm.ollama_coach import OllamaCoach
from src.infrastructure.llm.ollama_extractor import OllamaHabitExtractor
from src.infrastructure.llm.ollama_insight_formatter import OllamaInsightFormatter
from src.infrastructure.llm.ollama_summarizer import OllamaSummarizer
from src.infrastructure.scheduler.aps_scheduler import ReminderScheduler
from src.infrastructure.speech.faster_whisper_stt import FasterWhisperSTT
from src.infrastructure.telegram.notifier import TelegramNotifier


@dataclass
class UseCases:
    register_user: RegisterUserUseCase
    create_habit: CreateHabitUseCase
    update_habit: UpdateHabitUseCase
    complete_habit: CompleteHabitUseCase
    today_progress: GetTodayProgressUseCase
    coach_reply: CoachReplyUseCase
    extract_habits: ExtractHabitsFromTextUseCase
    process_voice: ProcessVoiceMessageUseCase
    log_mood: LogMoodUseCase
    mood_correlation: MoodCorrelationUseCase
    send_reminders: SendRemindersUseCase
    archive_goals: ArchiveExpiredGoalsUseCase
    complete_onboarding: CompleteOnboardingUseCase
    update_motivation_style: UpdateMotivationStyleUseCase
    # Аналитика и recovery (#1, #2, #3).
    generate_insights: GenerateInsightsUseCase
    assess_burnout: AssessBurnoutRiskUseCase
    toggle_recovery: ToggleRecoveryModeUseCase
    check_burnout: CheckBurnoutAndProposeRecoveryUseCase


class Container:
    """Собирает зависимости один раз и раздаёт нужные объекты."""

    def __init__(self, settings: Settings, bot: Bot) -> None:
        self.settings = settings
        self.bot = bot
        self.database = Database(settings.database_url)

        # Repositories
        self.users: UserRepository = SqlAlchemyUserRepository(self.database)
        self.habits: HabitRepository = SqlAlchemyHabitRepository(self.database)
        self.habit_logs: HabitLogRepository = SqlAlchemyHabitLogRepository(self.database)
        self.achievements: AchievementRepository = SqlAlchemyAchievementRepository(self.database)
        self.moods: MoodRepository = SqlAlchemyMoodRepository(self.database)
        self.coach_messages: CoachMessageRepository = SqlAlchemyCoachMessageRepository(self.database)

        # External services
        self.llm_coach: LLMCoach = GracefulCoach(
            OllamaCoach(host=settings.ollama_host, model=settings.ollama_model)
        )
        self.summarizer: LLMSummarizer = OllamaSummarizer(
            host=settings.ollama_host, model=settings.ollama_model
        )
        self.insight_formatter: LLMInsightFormatter = OllamaInsightFormatter(
            host=settings.ollama_host, model=settings.ollama_model
        )
        self.habit_extractor: HabitExtractor = OllamaHabitExtractor(
            host=settings.ollama_host, model=settings.ollama_model
        )
        self.stt: SpeechToText = FasterWhisperSTT(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )
        self.notifier: Notifier = TelegramNotifier(bot)
        self.exporter: ReportExporter = ReportExporterImpl(
            self.users, self.habits, self.habit_logs, self.moods
        )

        # Use cases
        # Создаём assess_burnout заранее — он нужен для check_burnout.
        assess_burnout = AssessBurnoutRiskUseCase(
            self.habits, self.habit_logs, self.moods,
        )
        self.use_cases = UseCases(
            register_user=RegisterUserUseCase(self.users),
            create_habit=CreateHabitUseCase(self.habits),
            update_habit=UpdateHabitUseCase(self.habits),
            complete_habit=CompleteHabitUseCase(
                self.users, self.habits, self.habit_logs, self.achievements
            ),
            today_progress=GetTodayProgressUseCase(self.habit_logs, self.users),
            coach_reply=CoachReplyUseCase(
                self.users, self.habits, self.habit_logs,
                self.coach_messages, self.llm_coach, self.summarizer,
            ),
            extract_habits=ExtractHabitsFromTextUseCase(self.habits, self.habit_extractor),
            process_voice=ProcessVoiceMessageUseCase(
                self.stt, self.habits,
                CompleteHabitUseCase(self.users, self.habits, self.habit_logs, self.achievements),
                ExtractHabitsFromTextUseCase(self.habits, self.habit_extractor),
            ),
            log_mood=LogMoodUseCase(self.moods),
            mood_correlation=MoodCorrelationUseCase(self.habits, self.habit_logs, self.moods),
            send_reminders=SendRemindersUseCase(
                self.users,
                GetTodayProgressUseCase(self.habit_logs, self.users),
                self.notifier,
            ),
            archive_goals=ArchiveExpiredGoalsUseCase(
                self.habits, self.habit_logs, self.notifier,
            ),
            complete_onboarding=CompleteOnboardingUseCase(self.users),
            update_motivation_style=UpdateMotivationStyleUseCase(self.users),
            generate_insights=GenerateInsightsUseCase(
                self.users, self.habits, self.habit_logs, self.moods,
                self.insight_formatter,
            ),
            assess_burnout=assess_burnout,
            toggle_recovery=ToggleRecoveryModeUseCase(self.users),
            check_burnout=CheckBurnoutAndProposeRecoveryUseCase(
                self.users, assess_burnout, self.notifier,
            ),
        )

        # Scheduler
        self.scheduler = ReminderScheduler(
            self.use_cases.send_reminders,
            self.use_cases.archive_goals,
            self.use_cases.check_burnout,
            self.use_cases.generate_insights,
            self.users,
            self.notifier,
        )

    async def dispose(self) -> None:
        self.scheduler.shutdown()
        await self.database.dispose()
