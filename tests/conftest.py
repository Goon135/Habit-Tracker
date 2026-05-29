"""Общие pytest-фикстуры.

Используем in-memory SQLite через aiosqlite для интеграционных тестов:
быстро, не требует Docker. Postgres-специфика покрывается отдельно при необходимости
(в текущем проекте upsert написан так, чтобы работать в обоих диалектах).
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
import pytest_asyncio

from src.infrastructure.database.database import Base, Database


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Database]:
    """Свежая in-memory БД для каждого теста.

    `sqlite+aiosqlite:///:memory:` создаёт уникальную базу на каждое подключение —
    это плохо для тестов, поэтому используем StaticPool через query string.
    """
    database = Database(
        "sqlite+aiosqlite:///file::memory:?cache=shared&uri=true",
        echo=False,
    )
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield database
    async with database.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await database.dispose()
