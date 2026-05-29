"""Подключение к БД через SQLAlchemy 2.0 async.

Используем PostgreSQL в продакшене и SQLite (aiosqlite) в тестах —
URL берётся из конфига, остальной код не меняется.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей."""


class Database:
    """Тонкая обёртка над AsyncEngine + sessionmaker. Хранит её один раз в DI-контейнере."""

    def __init__(self, dsn: str, echo: bool = False) -> None:
        self._engine: AsyncEngine = create_async_engine(dsn, echo=echo, future=True)
        self._session_factory = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self._engine.dispose()
