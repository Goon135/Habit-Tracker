"""Конфигурация приложения через переменные окружения.

Используем pydantic-settings — стандарт для type-safe конфигов в современном Python.
"""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(..., alias="BOT_TOKEN")
    database_url: str = Field(
        "postgresql+asyncpg://habitbot:habitbot@localhost:5432/habitbot",
        alias="DATABASE_URL",
    )

    # Ollama: локальный LLM-сервис на localhost:11434.
    # Если запускаешь Ollama на другом хосте/порту — поменяй здесь.
    ollama_host: str = Field("http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field("llama3.1:8b", alias="OLLAMA_MODEL")

    whisper_model_size: str = Field("small", alias="WHISPER_MODEL_SIZE")
    whisper_device: str = Field("cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field("int8", alias="WHISPER_COMPUTE_TYPE")

    log_level: str = Field("INFO", alias="LOG_LEVEL")
