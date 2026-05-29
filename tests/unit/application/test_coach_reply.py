"""CoachReply: проверяем, что A/B-разделение действительно влияет на путь.

Используем фейковый LLMCoach, который записывает, был ли вызван — это позволяет
утверждать, что LLM-группа реально дёргает модель, а template-группа — нет.
Это критичный тест для исследовательской части диплома.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.use_cases.coach_reply import CoachReplyUseCase
from src.domain.entities.coach_message import CoachMessage
from src.domain.entities.user import User
from src.domain.value_objects.coaching_mode import CoachingMode


@dataclass
class FakeUserRepo:
    users: dict[int, User] = field(default_factory=dict)

    async def get(self, uid):
        return self.users.get(uid)
    async def save(self, u):
        self.users[u.id] = u
    async def list_all_with_reminder(self):
        return list(self.users.values())


@dataclass
class FakeHabitRepo:
    async def add(self, h): h.id = 1; return h
    async def get(self, hid): return None
    async def list_for_user(self, uid, active_only=True): return []
    async def deactivate(self, hid, uid): pass


@dataclass
class FakeLogRepo:
    async def upsert(self, log): pass
    async def list_for_habit(self, hid, since): return []
    async def list_completed_dates(self, hid): return []
    async def today_status(self, uid, today): return []


@dataclass
class FakeCoachMessageRepo:
    messages: list[CoachMessage] = field(default_factory=list)

    async def add(self, m): self.messages.append(m)
    async def list_recent(self, uid, limit=20):
        return [m for m in self.messages if m.user_id == uid][-limit:]


@dataclass
class FakeLLM:
    called: int = 0
    last_message: str = ""
    last_history: list = field(default_factory=list)
    last_context: dict = field(default_factory=dict)

    async def reply(self, user_message, history, user_context):
        self.called += 1
        self.last_message = user_message
        self.last_history = list(history)
        self.last_context = dict(user_context)
        return f"[LLM] {user_message[::-1]}"  # дет-стерминированный ответ


@pytest.fixture
def setup():
    users = FakeUserRepo()
    habits = FakeHabitRepo()
    logs = FakeLogRepo()
    msgs = FakeCoachMessageRepo()
    llm = FakeLLM()
    uc = CoachReplyUseCase(users, habits, logs, msgs, llm)
    return uc, users, msgs, llm


@pytest.mark.asyncio
async def test_template_group_does_not_call_llm(setup):
    uc, users, msgs, llm = setup
    users.users[1] = User(id=1, username="u", first_name="A", coaching_mode=CoachingMode.TEMPLATE)

    reply = await uc.execute(user_id=1, user_message="сегодня сорвался, не выполнил")
    assert reply.mode == "template"
    assert llm.called == 0
    # Сообщение и ответ оба записаны в историю — нужно для аналитики A/B.
    assert len(msgs.messages) == 2


@pytest.mark.asyncio
async def test_llm_group_calls_llm_with_history_and_context(setup):
    uc, users, msgs, llm = setup
    users.users[2] = User(id=2, username="u", first_name="B", coaching_mode=CoachingMode.LLM)

    await uc.execute(user_id=2, user_message="как дела")
    await uc.execute(user_id=2, user_message="что-то лениво")

    assert llm.called == 2
    # На втором вызове история уже непустая.
    assert len(llm.last_history) >= 2
    # Контекст содержит имя пользователя.
    assert llm.last_context.get("first_name") == "B"


@pytest.mark.asyncio
async def test_template_keyword_matching(setup):
    uc, users, msgs, llm = setup
    users.users[3] = User(id=3, username="u", first_name="C", coaching_mode=CoachingMode.TEMPLATE)

    # "сорвал" — relapse → ответ из relapse-пула.
    from src.application.use_cases.coach_reply import _TEMPLATES_RELAPSE
    reply = await uc.execute(user_id=3, user_message="опять сорвался")
    assert reply.text in _TEMPLATES_RELAPSE
