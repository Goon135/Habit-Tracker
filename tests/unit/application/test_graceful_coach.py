"""GracefulCoach: поведение при rate limit и cooldown.

Тестируем без реального Gemini — внутренний LLMCoach подменён на фейк, который
по желанию бросает исключения с сообщениями, похожими на ошибки Gemini API.
"""
from __future__ import annotations

import pytest

from src.infrastructure.llm.graceful_coach import GracefulCoach


class _FakeInner:
    def __init__(self, behavior="ok", reply_text="настоящий ответ"):
        self.behavior = behavior
        self.reply_text = reply_text
        self.calls = 0

    async def reply(self, user_message, history, user_context):
        self.calls += 1
        if self.behavior == "ok":
            return self.reply_text
        if self.behavior == "rate_limit":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: Quota exceeded for model")
        if self.behavior == "server_error":
            raise RuntimeError("500 Internal Server Error")
        raise AssertionError(f"unknown behavior: {self.behavior}")


@pytest.mark.asyncio
async def test_normal_path_returns_inner_reply():
    inner = _FakeInner(behavior="ok")
    coach = GracefulCoach(inner)
    text = await coach.reply("привет", [], {})
    assert text == "настоящий ответ"
    assert inner.calls == 1


@pytest.mark.asyncio
async def test_rate_limit_returns_fallback_and_enters_cooldown():
    inner = _FakeInner(behavior="rate_limit")
    coach = GracefulCoach(inner, cooldown_seconds=60)

    text = await coach.reply("привет", [], {})
    assert "отдыхаю" in text  # из шаблона fallback
    assert inner.calls == 1

    # Второй вызов сразу — даже не должен дойти до inner.
    text2 = await coach.reply("ещё", [], {})
    assert "отдыхаю" in text2
    assert inner.calls == 1  # inner НЕ был вызван повторно


@pytest.mark.asyncio
async def test_cooldown_expires_and_inner_is_called_again(monkeypatch):
    """После истечения cooldown снова пробуем inner. Манипулируем monotonic time."""
    import src.infrastructure.llm.graceful_coach as gc_mod

    fake_now = [1000.0]
    monkeypatch.setattr(gc_mod.time, "monotonic", lambda: fake_now[0])

    inner = _FakeInner(behavior="rate_limit")
    coach = GracefulCoach(inner, cooldown_seconds=60)

    await coach.reply("привет", [], {})
    assert inner.calls == 1

    # Перематываем время на 61 секунду вперёд — cooldown истёк.
    fake_now[0] += 61

    # Теперь меняем поведение inner на нормальное — должен пройти.
    inner.behavior = "ok"
    text = await coach.reply("снова", [], {})
    assert text == "настоящий ответ"
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_non_rate_limit_errors_propagate():
    """5xx и сетевые ошибки не должны маскироваться fallback'ом — пусть use case логирует."""
    inner = _FakeInner(behavior="server_error")
    coach = GracefulCoach(inner)
    with pytest.raises(RuntimeError, match="500"):
        await coach.reply("привет", [], {})
