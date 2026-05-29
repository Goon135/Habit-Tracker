# HabitBot 2.0 — AI-coach Telegram bot

Дипломный проект: трекер привычек с AI-коучем на базе Claude, локальным
распознаванием голоса (faster-whisper), анализом настроения и A/B-экспериментом
для сравнения LLM-генерируемой обратной связи с шаблонной.

## Возможности

- AI-коуч (локальный Ollama + Llama 3.1 8B) с поддержкой диалогового контекста.
- A/B-эксперимент: пользователи детерминированно делятся пополам на
  `template` и `llm` группы для исследовательской части диплома. История
  диалога логируется в обеих группах.
- Извлечение привычек из произвольного текста через function calling
  («хочу начать бегать по утрам и читать перед сном» → две привычки).
- Голосовой ввод: voice → faster-whisper → отметка или создание привычки.
- Геймификация (очки, уровни, достижения).
- Настроение 1–5 и корреляция с выполнением привычек.
- Экспорт CSV и PDF.
- Напоминания через APScheduler с persistent job store в Postgres.

## Архитектура

Clean Architecture, 4 слоя. Зависимости направлены строго внутрь:
`presentation → application → domain`, `infrastructure` реализует Protocol'ы
из `domain`/`application` и подключается через DI-контейнер.

```
src/
├── domain/                # бизнес-сущности, value objects, доменные сервисы,
│   │                      # Protocol'ы репозиториев. Никаких внешних зависимостей.
│   ├── entities/
│   ├── value_objects/
│   ├── services/
│   └── repositories/
├── application/           # use cases, DTO, Protocol'ы внешних сервисов
│   ├── use_cases/
│   ├── dto/
│   └── interfaces/
├── infrastructure/        # SQLAlchemy, Anthropic, faster-whisper, APScheduler,
│   │                      # экспорт, Telegram-обёртки, конфиг, DI-контейнер
│   ├── database/
│   ├── llm/
│   ├── speech/
│   ├── scheduler/
│   ├── export/
│   ├── telegram/
│   ├── config.py
│   └── container.py
└── presentation/          # aiogram-хэндлеры, клавиатуры
    ├── handlers/
    └── keyboards/
```

Принцип проверяется так: импорт чего-либо из `infrastructure` или `aiogram`
в `domain/` или `application/` должен быть отсутствовать. Это даёт:

- Юнит-тесты use case'ов без БД и сети (см. `tests/unit/application/`).
- Свободу заменить Postgres, LLM-провайдера или Telegram на что-то другое
  без изменений в бизнес-логике.

## Запуск

Полная пошаговая инструкция — в [SETUP.md](SETUP.md). Краткая выжимка для тех, кто уже всё развернул:

### 1. PostgreSQL

**Windows (рекомендуется):** установи PostgreSQL 17 нативно с https://www.postgresql.org/download/windows/. Создай пользователя и базу:
```
CREATE USER habitbot WITH PASSWORD 'habitbot';
CREATE DATABASE habitbot OWNER habitbot;
```

**Linux/macOS:** можно через Docker:
```bash
docker compose up -d postgres
```

### 2. Python и зависимости

```bash
python3.12 -m venv .venv
source .venv/bin/activate    # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### 3. Конфиг

```bash
cp .env.example .env
# отредактируй .env: BOT_TOKEN (см. SETUP.md)
```

### 4. Миграции

```bash
alembic upgrade head
```

Создать новую миграцию после изменения моделей:

```bash
alembic revision --autogenerate -m "описание"
```

### 5. Запуск

```bash
python -m src
# или после установки:
habitbot
```

## Тесты

```bash
pytest                                # все тесты
pytest --cov=src --cov-report=term-missing
pytest tests/unit/                    # только юниты, без БД
```

Текущая обвязка покрывает: domain (Streak, Frequency, CoachingMode,
gamification, achievements), ключевые use cases (CompleteHabit, CoachReply,
MoodCorrelation) с fake-репозиториями, GracefulCoach с graceful degradation,
интеграционный тест SQLAlchemy на in-memory SQLite. 38 тестов, шаблон даёт
основу для доведения покрытия до 70% — нужно дописать тесты по остальным use
cases (`ExtractHabits`, `ProcessVoice`, `SendReminders`), репозиториям и
интеграционно — экспортёру.

## A/B-эксперимент (исследовательская часть)

Назначение группы — детерминированный hash MD5 от user_id с солью.
Изменение соли в `CoachingMode.assign(salt=...)` запускает новый раунд
эксперимента без потери совместимости со старыми данными.

Все взаимодействия с коучем (вход и ответ) логируются в таблицу
`coach_messages` с привязкой к user_id. Это позволяет в Jupyter:

- посчитать retention (D1/D7/D30) по группам,
- сравнить completion rate привычек,
- измерить распределение длины серий,
- провести χ²-тест на разнице вероятностей возврата к выполнению после срыва.

Пример SQL-выборки для анализа в notebook:

```sql
SELECT u.coaching_mode, COUNT(DISTINCT l.user_id) AS active_users,
       AVG(streak_length) AS avg_streak
FROM users u
JOIN habit_logs l ON l.user_id = u.id
JOIN (...) streak_calc ON ...
GROUP BY u.coaching_mode;
```

## Стек

| Слой | Технология |
| --- | --- |
| Bot framework | aiogram 3.x |
| ORM | SQLAlchemy 2.0 async |
| Migrations | Alembic |
| Database | PostgreSQL 17 (prod, нативно на хост или Docker), SQLite (tests) |
| LLM | Ollama (локально) + Llama 3.1 8B — бесплатно, оффлайн, без API-ключей |
| Speech-to-text | faster-whisper (локально) |
| Scheduler | APScheduler с SQLAlchemyJobStore |
| Reports | ReportLab + csv |
| Config | pydantic-settings |
| Tests | pytest + pytest-asyncio + pytest-cov |
