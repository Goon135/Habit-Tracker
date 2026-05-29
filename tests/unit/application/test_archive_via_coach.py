"""Тесты архивации привычки через диалог с LLM-коучем.

Сценарии:
- пользователь просит удалить привычку → коуч вызывает archive_habit →
  use case архивирует и пишет подтверждение в ответ;
- название привычки не совпадает дословно — поиск по подстроке;
- LLM запросил архивацию несуществующей привычки → use case говорит
  «не нашёл» вместо обмана;
- после архивации memory_summary очищается, чтобы коуч не «помнил»
  удалённую привычку.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from src.application.interfaces.ai_services import CoachAction
from src.application.use_cases.archive_habit import ArchiveHabitUseCase
from src.application.use_cases.coach_reply import CoachReplyUseCase
from src.domain.entities.coach_message import CoachMessage
from src.domain.entities.habit import Habit
from src.domain.entities.user import User
from src.domain.value_objects.category import Category
from src.domain.value_objects.coaching_mode import CoachingMode


@dataclass
class FakeUserRepo:
    users: dict = field(default_factory=dict)
    async def get(self, uid): return self.users.get(uid)
    async def save(self, u): self.users[u.id] = u
    async def list_all_with_reminder(self): return list(self.users.values())


@dataclass
class FakeHabitRepo:
    """Хранит привычки в памяти, поддерживает deactivate."""
    habits: list = field(default_factory=list)

    async def add(self, h):
        h.id = len(self.habits) + 1
        self.habits.append(h)
        return h
    async def get(self, hid):
        for h in self.habits:
            if h.id == hid:
                return h
        return None
    async def list_for_user(self, uid, active_only=True):
        return [h for h in self.habits if h.user_id == uid and (not active_only or h.is_active)]
    async def deactivate(self, hid, uid):
        for h in self.habits:
            if h.id == hid and h.user_id == uid:
                h.is_active = False


@dataclass
class FakeLogRepo:
    async def list_completed_dates(self, hid): return []


@dataclass
class FakeMessageRepo:
    messages: list = field(default_factory=list)
    async def add(self, m): self.messages.append(m)
    async def list_recent(self, uid, limit=20):
        return [m for m in self.messages if m.user_id == uid][-limit:]


@dataclass
class ScriptedLLM:
    """LLM с заранее заданными действиями для каждого вызова."""
    actions: list = field(default_factory=list)
    calls: int = 0

    async def reply(self, user_message, history, user_context):
        action = self.actions[self.calls] if self.calls < len(self.actions) else CoachAction(text="ок")
        self.calls += 1
        return action


def _make_use_case(habits, llm):
    users = FakeUserRepo()
    msgs = FakeMessageRepo()
    archive = ArchiveHabitUseCase(habits)
    uc = CoachReplyUseCase(
        users=users,
        habits=habits,
        habit_logs=FakeLogRepo(),
        coach_messages=msgs,
        llm_coach=llm,
        summarizer=None,
        archive_habit=archive,
    )
    return uc, users, msgs


@pytest.mark.asyncio
async def test_coach_archives_habit_when_llm_asks():
    """Главный happy-path: LLM попросил архивировать «Бегать», use case делает."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Бегать", category=Category.SPORT))
    await habits.add(Habit(id=None, user_id=1, name="Читать", category=Category.LEARNING))

    llm = ScriptedLLM(actions=[
        CoachAction(text="Хорошо, убрал.", archive_habit_names=["Бегать"]),
    ])
    uc, users, _ = _make_use_case(habits, llm)
    users.users[1] = User(id=1, username="u", first_name="A", coaching_mode=CoachingMode.LLM)

    reply = await uc.execute(1, "удали привычку бегать")

    # Подтверждение в тексте.
    assert "«Бегать»" in reply.text
    assert "удалена" in reply.text.lower()
    # Привычка реально не активна в репо.
    active = await habits.list_for_user(1, active_only=True)
    assert len(active) == 1
    assert active[0].name == "Читать"


@pytest.mark.asyncio
async def test_archive_by_substring_match():
    """Пользователь сказал «бег», в БД «Бегать по утрам» — должно работать."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Бегать по утрам", category=Category.SPORT))

    llm = ScriptedLLM(actions=[
        CoachAction(text="", archive_habit_names=["бег"]),  # неточное имя
    ])
    uc, users, _ = _make_use_case(habits, llm)
    users.users[1] = User(id=1, username="u", first_name="A", coaching_mode=CoachingMode.LLM)

    reply = await uc.execute(1, "убери бег")
    assert "«Бегать по утрам»" in reply.text
    active = await habits.list_for_user(1, active_only=True)
    assert active == []


@pytest.mark.asyncio
async def test_archive_nonexistent_habit_reports_not_found():
    """LLM запросил привычку, которой нет — use case это сообщает."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Читать", category=Category.LEARNING))

    llm = ScriptedLLM(actions=[
        CoachAction(text="", archive_habit_names=["плавание"]),
    ])
    uc, users, _ = _make_use_case(habits, llm)
    users.users[1] = User(id=1, username="u", first_name="A", coaching_mode=CoachingMode.LLM)

    reply = await uc.execute(1, "удали плавание")
    assert "не нашёл" in reply.text.lower()
    # Существующая привычка не тронута.
    active = await habits.list_for_user(1, active_only=True)
    assert len(active) == 1


@pytest.mark.asyncio
async def test_archive_clears_memory_summary():
    """После архивации memory_summary должна обнулиться,
    иначе в следующих сообщениях коуч продолжит видеть удалённую привычку."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Бегать", category=Category.SPORT))

    llm = ScriptedLLM(actions=[
        CoachAction(text="ок", archive_habit_names=["Бегать"]),
    ])
    uc, users, _ = _make_use_case(habits, llm)
    users.users[1] = User(
        id=1, username="u", first_name="A",
        coaching_mode=CoachingMode.LLM,
        memory_summary="Пользователь любит бегать по утрам.",
        memory_updated_at=datetime.utcnow(),
    )

    await uc.execute(1, "убери бег")
    user_after = users.users[1]
    assert user_after.memory_summary == ""
    assert user_after.memory_updated_at is None


@pytest.mark.asyncio
async def test_normal_dialog_does_not_archive_anything():
    """Без archive_habit_names не должно быть никаких удалений."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Читать", category=Category.LEARNING))

    llm = ScriptedLLM(actions=[CoachAction(text="Расскажи подробнее")])
    uc, users, _ = _make_use_case(habits, llm)
    users.users[1] = User(id=1, username="u", first_name="A", coaching_mode=CoachingMode.LLM,
                          memory_summary="что-то о привычке")

    reply = await uc.execute(1, "у меня тяжелый день")
    assert reply.text == "Расскажи подробнее"
    active = await habits.list_for_user(1, active_only=True)
    assert len(active) == 1
    # memory не трогаем при обычном диалоге.
    assert users.users[1].memory_summary == "что-то о привычке"


@pytest.mark.asyncio
async def test_archive_use_case_by_id_basic():
    """Прямой вызов by_id из UI — архивирует привычку и возвращает результат."""
    habits = FakeHabitRepo()
    h = await habits.add(Habit(id=None, user_id=1, name="Йога", category=Category.SPORT))
    archive = ArchiveHabitUseCase(habits)

    result = await archive.by_id(user_id=1, habit_id=h.id)
    assert result is not None
    assert result.archived_habit_name == "Йога"
    active = await habits.list_for_user(1, active_only=True)
    assert active == []


@pytest.mark.asyncio
async def test_archive_use_case_by_id_other_user_rejected():
    """by_id с чужим user_id ничего не делает (защита от подделки запроса)."""
    habits = FakeHabitRepo()
    h = await habits.add(Habit(id=None, user_id=1, name="Йога", category=Category.SPORT))
    archive = ArchiveHabitUseCase(habits)

    result = await archive.by_id(user_id=999, habit_id=h.id)
    assert result is None
    active = await habits.list_for_user(1, active_only=True)
    assert len(active) == 1  # не тронута


@pytest.mark.asyncio
async def test_archive_use_case_by_name_case_insensitive():
    """Регистр в имени не должен мешать."""
    habits = FakeHabitRepo()
    await habits.add(Habit(id=None, user_id=1, name="Медитация", category=Category.MINDFULNESS))
    archive = ArchiveHabitUseCase(habits)

    result = await archive.by_name(user_id=1, name_query="МЕДИТАЦИЯ")
    assert result is not None
    assert result.archived_habit_name == "Медитация"
