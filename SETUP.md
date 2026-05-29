# Запуск HabitBot на Windows — пошаговая инструкция

Для **Windows 10/11 нативно** (без WSL). Если на каком-то шаге что-то идёт не так — стоп, разбирайся, пока не починишь, и только потом двигайся дальше.

Время полного прохождения по первому разу: **40–90 минут**, из которых ~10 минут уйдёт на скачивание Whisper-модели при первом запуске бота.

---

## ⚠️ Критичные предупреждения, прочти ДО старта

1. **Python должен быть 3.12, а не 3.13.** На Python 3.13 не ставится `ctranslate2` (зависимость faster-whisper) — нет wheel'ов. Если у тебя уже стоит 3.13 — это нормально, поставим 3.12 рядом, они не конфликтуют.
2. **Не ставь Python из Microsoft Store.** Он работает в песочнице и часто ломает venv. Только установщик с python.org.
3. **Все команды — в PowerShell**, не в cmd.exe. Открывается через `Win+X → Terminal` или `Win+R → powershell`.
4. **Если PowerShell ругается «cannot be loaded because running scripts is disabled»** — выполни один раз в PowerShell от админа:
   ```powershell
   Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
   ```
   Это нужно для активации venv.

---

## Содержание

1. [Получение токенов](#1-получение-токенов)
2. [Установка Python 3.12](#2-установка-python-312)
3. [Установка PostgreSQL 17 нативно](#3-установка-postgresql-17-нативно)
4. [Установка Ollama (локальный LLM)](#4-установка-ollama-локальный-llm)
5. [Распаковка проекта](#5-распаковка-проекта)
6. [Виртуальное окружение и пакеты](#6-виртуальное-окружение-и-пакеты)
7. [Проверка PostgreSQL](#7-проверка-postgresql)
8. [Настройка .env](#8-настройка-env)
9. [Миграции БД](#9-миграции-бд)
10. [Прогон тестов](#10-прогон-тестов)
11. [Запуск бота](#11-запуск-бота)
12. [Проверка фич в Telegram](#12-проверка-фич-в-telegram)
13. [Если не работает](#13-если-не-работает)

---

## 1. Получение токенов

### 1.1. Telegram Bot Token

1. В Telegram найди `@BotFather`.
2. Отправь ему `/newbot`.
3. Имя: `My Diploma Habit Bot` (любое).
4. Username: должен заканчиваться на `bot`, например `mydiplomahabit_bot`.
5. BotFather пришлёт сообщение со строкой вида `123456789:ABCdef-GhIJklmNOpqrSTUvwXYz`.
6. **Скопируй её в блокнот** — это твой `BOT_TOKEN`.

### 1.2. Ollama — локальный LLM (без регистрации, без VPN)

Ollama — это локальный сервер языковых моделей. Качаешь его один раз, потом он крутится на твоей машине и обслуживает бота. Никаких API-ключей, никакой регистрации, никаких квот.

> **Почему Ollama?**
> - **Бесплатно навсегда**, никаких ключей и регистраций.
> - **Доступен из любой страны** — никаких санкций, региональных ограничений, VPN.
> - **Работает оффлайн** — на демо защиты диплома ничего не сломается из-за того, что у провайдера упал сервер или кончились лимиты.
> - **Данные пользователя не уходят в облако** — это плюс для дипломной работы про трекер привычек.
> - **На GPU быстрый**: 1-3 секунды на ответ.
>
> Минусы: модель занимает место (~5 ГБ), при первой загрузке требуется интернет для скачивания.

Установка делается в секции 3 (после установки Postgres). Пока что **просто проверь**, что у тебя:
- **8+ ГБ оперативки** (или дискретная NVIDIA с 4+ ГБ VRAM).
- **6+ ГБ свободного места** на диске для модели.

Если железо слабее — есть план Б (модель `llama3.2:3b`, занимает 2 ГБ), его упомяну в секции 3.

---

## 2. Установка Python 3.12

> ⚠️ Не 3.13. Не из Microsoft Store. Только 3.12 с python.org.

1. Открой https://www.python.org/downloads/windows/
2. Найди раздел **Python 3.12.x** (любая последняя версия 3.12, например 3.12.8). Скачай **Windows installer (64-bit)**.
3. Запусти установщик.
4. **На первом экране ОБЯЗАТЕЛЬНО поставь галочку `Add python.exe to PATH`** внизу окна. Без этого `python` не будет работать из терминала.
5. Нажми `Install Now` (или `Customize installation` если хочешь поменять путь — но не обязательно).
6. Дождись установки, закрой установщик.

**Проверь:** открой **новое** окно PowerShell (Win+X → Terminal):

```powershell
py -3.12 --version
```

Должно вывести `Python 3.12.x`. Если выводит «Python was not found» или версию 3.13 — см. секцию 12.

> Если у тебя на компе уже стоит Python 3.13 — он останется. Команда `py -3.12` гарантированно запустит именно 3.12, какие бы версии ещё ни были установлены.

---

## 3. Установка PostgreSQL 17 нативно

Идём именно по нативной установке, потому что Docker Desktop на Windows часто конфликтует с `asyncpg` (нестабильно работает TCP-handshake через WSL2-сеть Docker'а — известная проблема). Нативный Postgres надёжнее и в защите диплома смотрится лучше: «PostgreSQL 17 устанавливается на хост».

> Если очень хочется через Docker — это работает в Linux/macOS и через WSL2. В корне проекта есть `docker-compose.yml`. На нативном Windows — не рекомендую.

1. Открой https://www.postgresql.org/download/windows/ → нажми **Download the installer** → попадёшь на сайт EDB.
2. Скачай **PostgreSQL 17.x for Windows x86-64**. Обязательно версия 17 и обязательно x86-64 (не x86).
3. Запусти установщик **от админа**.

В процессе установки:

- **Installation Directory** — оставь по умолчанию (`C:\Program Files\PostgreSQL\17`).
- **Select Components** — оставь все галки: `PostgreSQL Server`, `pgAdmin 4`, `Stack Builder`, `Command Line Tools`. Stack Builder в конце спросит про доп. компоненты — **пропусти его** (закрой окно).
- **Data Directory** — по умолчанию.
- **Password** — пароль для суперпользователя `postgres`. Поставь `postgres` (для локалки нормально). **Запомни.**
- **Port** — `5432`.
- **Locale** — `Default locale`.

После установки служба `postgresql-x64-17` стартанёт сама и будет запускаться при загрузке Windows. Проверь:

```powershell
Get-Service -Name "postgresql*"
```

Должна быть строка `Running postgresql-x64-17`. Если `Stopped` — `Start-Service postgresql-x64-17`.

### 3.1. Создание базы и пользователя для бота

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1
```

Введёт пароль `postgres`. В psql:

```sql
CREATE USER habitbot WITH PASSWORD 'habitbot';
CREATE DATABASE habitbot OWNER habitbot;
\q
```

### 3.2. Проверка коннекта под новым пользователем

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U habitbot -d habitbot -h 127.0.0.1 -c "SELECT 1;"
```

Введёт пароль `habitbot`. Должна вернуться таблица с единицей. Если так — переходи дальше.

> Если psql ругается «password authentication failed» или коннект обрывается с `ConnectionResetError` — скорее всего, у тебя ещё стоит старая версия Postgres (например, 16), которая мешает. Проверь:
> ```powershell
> Get-WmiObject Win32_Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object Name, State, PathName
> ```
> Если в списке несколько — удали старые через Control Panel → Programs.

---

## 4. Установка Ollama (локальный LLM)

### 4.1. Установка

1. Открой https://ollama.com/download → нажми **Download for Windows**.
2. Запусти `OllamaSetup.exe`. Установка минимальная — никаких опций, просто Next.
3. После установки в трее появится иконка Ollama (бегущая лама). Это значит, что фоновая служба `ollama.exe` запущена и слушает `localhost:11434`.

**Проверка, что Ollama жива:**

```powershell
ollama --version
```

И что REST API отвечает:

```powershell
curl http://localhost:11434/api/version
```

Должна вернуться JSON-строка с версией. Если ошибка — Ollama не запущена; перезапусти её через ярлык в меню Пуск.

### 4.2. Скачивание модели

```powershell
ollama pull llama3.1:8b
```

Скачается **~4.7 ГБ** (это квантованная Q4 версия — стандарт для Ollama). Время — 5-15 минут в зависимости от интернета.

**Проверка, что модель работает:**

```powershell
ollama run llama3.1:8b "Привет! Ответь одним предложением по-русски."
```

Должна ответить осмысленной русской фразой. На GPU — за 1-3 секунды, на CPU — за 5-15 секунд. После проверки нажми `Ctrl+D` или `/bye` чтобы выйти.

### 4.3. Если железо слабое

Если у тебя меньше 8 ГБ RAM или нет GPU и `llama3.1:8b` ползёт по полчаса:

```powershell
ollama pull llama3.2:3b
```

Это всего 2 ГБ, отвечает быстрее, качество русского чуть похуже. В `.env` тогда поменяй `OLLAMA_MODEL=llama3.2:3b`.

### 4.4. (Опционально) Проверка использования GPU

Если у тебя NVIDIA-видяха, Ollama должна сама её подхватить через CUDA. Проверь:

```powershell
ollama ps
```

Покажет колонку **PROCESSOR**: если там `100% GPU` — отлично. Если `100% CPU` — модель крутится на процессоре. Это означает либо что у тебя VRAM недостаточно (попробуй `llama3.2:3b`), либо что Ollama не нашла CUDA. Обычно это решается обновлением драйверов NVIDIA.

---

## 5. Распаковка проекта

1. Скачай `habitbot.zip` (тебе уже его выдали).
2. **Не распаковывай в Downloads** — там часто странности с правами. Распакуй в простую папку, например `C:\projects\habitbot`.
3. Открой PowerShell и перейди туда:

```powershell
cd C:\projects\habitbot
```

Проверка, что ты в нужной папке:

```powershell
ls
```

Должны быть видны `src`, `tests`, `alembic`, `pyproject.toml`, `docker-compose.yml`, `README.md` и другие.

---

## 6. Виртуальное окружение и пакеты

Виртуальное окружение (venv) — это изолированная папка с Python и пакетами проекта. Без venv пакеты ставятся глобально, и через год у тебя будет каша из конфликтующих версий.

### 5.1. Создание venv

```powershell
py -3.12 -m venv .venv
```

Появится папка `.venv` (в которой ~30 МБ файлов Python). Это нормально.

### 5.2. Активация venv

```powershell
.\.venv\Scripts\Activate.ps1
```

После активации в начале строки PowerShell появится `(.venv)`. **Этот префикс должен присутствовать на ВСЕХ дальнейших шагах работы с проектом.** Если открыл новое окно — активируй venv заново.

> Если PowerShell пишет «cannot be loaded because running scripts is disabled» — см. предупреждение в начале документа про `Set-ExecutionPolicy`.

### 5.3. Обновление pip

```powershell
python -m pip install --upgrade pip
```

### 5.4. Установка проекта

```powershell
pip install -e ".[dev]"
```

Это займёт **3–7 минут**. pip скачает aiogram, SQLAlchemy, asyncpg, alembic, APScheduler, ollama, faster-whisper, reportlab, pydantic-settings, pytest и десятки транзитивных пакетов.

**Что может пойти не так:**
- Если упадёт на `ctranslate2` с ошибкой «no matching distribution found» — у тебя всё-таки Python 3.13, а не 3.12. Удали `.venv` (`Remove-Item -Recurse -Force .venv`) и пересоздай через `py -3.12 -m venv .venv`.

### 5.5. Проверка

```powershell
python -c "import aiogram, sqlalchemy, anthropic, faster_whisper, reportlab; print('OK')"
```

Должно напечатать `OK`. Если нет — стоп, разбирайся по сообщению об ошибке.

> **FFmpeg отдельно ставить НЕ нужно.** faster-whisper использует PyAV, который тащит FFmpeg внутри себя. Это специфика именно нативного Windows-варианта — в Linux/macOS-инструкциях обычно пишут «поставь ffmpeg», и это создаёт ложное впечатление, что он обязателен. Здесь — не обязателен.

---

## 7. Проверка PostgreSQL

Постгрес ты уже установил и проверил в секции 3 — здесь только убедимся, что служба запущена и БД создана:

```powershell
Get-Service -Name "postgresql*"
```

`Running postgresql-x64-17` → всё ок. Если `Stopped` → `Start-Service postgresql-x64-17`.

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U habitbot -d habitbot -h 127.0.0.1 -c "SELECT 1;"
```

Введёт пароль `habitbot`. Должно вернуть единицу.

---

## 8. Настройка .env

Скопируй шаблон:

```powershell
copy .env.example .env
```

Открой `.env` в любом редакторе. Если установлен VS Code:

```powershell
code .env
```

Или просто блокнотом:

```powershell
notepad .env
```

**Заполни поле `BOT_TOKEN`:**

```
BOT_TOKEN=123456789:ABCdef-GhIJklmNOpqrSTUvwXYz
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

`OLLAMA_HOST` и `OLLAMA_MODEL` уже идут со значениями по умолчанию — если ты следовал секции 4, менять не надо. Если ставил модель `llama3.2:3b` для слабого железа — поправь `OLLAMA_MODEL=llama3.2:3b`.

Вставь значения, которые сохранил в блокноте на шаге 1. **Без кавычек, без пробелов до/после `=`.**

Остальные настройки уже подходят для локалки, менять не надо. Если на шаге 6 ты менял порт на 5433, тогда поправь `DATABASE_URL`:

```
DATABASE_URL=postgresql+asyncpg://habitbot:habitbot@localhost:5433/habitbot
```

Сохрани файл и закрой.

---

## 9. Миграции БД

Применяем начальную миграцию — она создаёт все 6 таблиц:

```powershell
alembic upgrade head
```

Должно вывести что-то вроде:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial, initial schema
```

**Проверь:**

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U habitbot -d habitbot -h 127.0.0.1 -c "\dt"
```

Должны быть 6 таблиц: `users`, `habits`, `habit_logs`, `achievements`, `mood_entries`, `coach_messages`. Если их нет — миграция не прошла; вернись и смотри лог `alembic upgrade head`.

---

## 10. Прогон тестов

Тесты не требуют ни Telegram, ни Ollama, ни Whisper, ни даже Postgres — они работают на in-memory SQLite. Это первая реальная проверка, что проект собран и установлен корректно.

```powershell
pytest
```

Ожидаемый результат: **38 passed**. Если что-то падает — стоп, разбирайся по сообщению. Эти тесты — твой safety net: если они зелёные, значит, ядро бизнес-логики точно работает.

С покрытием:

```powershell
pytest --cov=src --cov-report=term-missing
```

Сейчас покрытие domain+application ~69%. Чтобы добить до 70%+, скопируй `tests/unit/application/test_complete_habit.py` как шаблон и напиши тесты для `RegisterUserUseCase`, `CreateHabitUseCase` и т.д.

---

## 11. Запуск бота

Финальная проверка перед запуском — все эти галочки должны быть отмечены:

- ✅ В начале строки PowerShell видно `(.venv)`. Если нет — `.\.venv\Scripts\Activate.ps1`.
- ✅ Служба Postgres запущена: `Get-Service postgresql-x64-17` → `Running`.
- ✅ Ollama запущена: иконка ламы в трее. Если нет — запусти из меню Пуск.
- ✅ Модель скачана: `ollama list` показывает `llama3.1:8b` (или другую из `.env`).
- ✅ В `.env` заполнен `BOT_TOKEN` (без кавычек).
- ✅ `pytest` зелёный.

Запускаем:

```powershell
python -m src
```

### Что происходит при первом запуске

⚠️ **30–90 секунд тишины** — это faster-whisper скачивает модель `small` (~480 МБ) в папку `C:\Users\<имя>\.cache\huggingface\`. В консоли никаких сообщений. Это нормально, не паникуй и не убивай процесс. На последующих запусках модель уже закэширована и старт мгновенный.

После загрузки модели увидишь:
```
2026-05-23 12:34:56 [INFO] habitbot: APScheduler started
2026-05-23 12:34:56 [INFO] habitbot: 🚀 Бот запущен
```

Всё. Бот слушает Telegram, AI-коуч и распознавание привычек на Anthropic, планировщик отрабатывает каждую минуту, голосовые расшифровываются локально на CPU.

**Остановка:** `Ctrl+C` в PowerShell. Иногда нужно нажать дважды — нормально.

---

## 12. Проверка фич в Telegram

Открой Telegram, найди своего бота по username и пройди этот чеклист — он покажет, что все 9 пунктов диплома реально работают.

### 11.1. Регистрация и A/B-разделение

- [ ] `/start` → бот приветствует, показывает меню.
- [ ] `/profile` → в самом низу видно `A/B группа: llm` или `template`. Запомни — она зафиксирована за тобой навсегда (детерминированный хэш от твоего user_id).

### 11.2. Распознавание привычек из текста (LLM tool use)

Без всяких кнопок отправь:
```
хочу начать бегать по утрам и читать перед сном
```

- [ ] Бот должен ответить «Я понял, что ты хочешь начать:» с **двумя** привычками и категориями (Спорт + Обучение или похожими).

### 11.3. Создание привычки через кнопку

- [ ] `➕ Новая привычка` → введи название → выбери категорию → видишь «✅ Привычка ... создана!».

### 11.4. Отметка выполнения и геймификация

- [ ] `✅ Отметить сегодня` → нажми на одну из своих привычек.
- [ ] Получаешь сообщение с +10 очков, серией = 1 день, достижением «🌱 Первый шаг».

### 11.5. AI-коуч

- [ ] `💬 AI-коуч` → бот переходит в режим диалога.
- [ ] Напиши: «сегодня сорвался, не выполнил привычку».
- [ ] Если ты в группе **llm** — ответ длинный, осмысленный, учитывает твои привычки.
- [ ] Если в группе **template** — короткий ответ из заготовленного пула (он содержит слова «срывы — часть процесса», «один пропуск не ломает» и т.п.).
- [ ] Выход: `/stop`.

### 11.6. Голосовой ввод 🎙

- [ ] В чате нажми и удерживай микрофон, скажи: **«отметь медитацию»** (если есть такая привычка) или название другой.
- [ ] Бот ответит «🎙 Услышал: ...» и отметит привычку.
- [ ] Скажи: **«хочу медитировать каждый день»** — создаст новую привычку.

> **Первое голосовое после запуска** обрабатывается дольше (модель прогревается, 15-30 секунд). Последующие — секунды.

### 11.7. Настроение

- [ ] `😊 Настроение` → выбери оценку 1-5.
- [ ] `/insights` сразу не покажет ничего — нужно несколько отметок за разные дни. Для демо см. секцию ниже.

### 11.8. Экспорт

- [ ] `📤 Экспорт` → нажми CSV → получи файл, открой Excel'ом (кириллица должна быть нормальной благодаря BOM).
- [ ] То же с PDF.

### 11.9. Напоминания

- [ ] `⚙️ Настройки` → `⏰ Время напоминаний` → введи время **на 2 минуты вперёд** (например, если сейчас 14:30 — введи `14:32`).
- [ ] Через 1-2 минуты бот сам пришлёт напоминание о невыполненных привычках.

### Быстрое наполнение данными для демо корреляций

`/insights` требует хотя бы 3 отметки настроения и историю выполнения привычек. Чтобы не ждать неделями, закинь синтетику напрямую в БД. Сначала узнай свой telegram user_id через `/profile`.

```powershell
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U habitbot -d habitbot -h 127.0.0.1
```

В psql:

```sql
-- Замени 123456789 на свой telegram user_id
INSERT INTO mood_entries (user_id, entry_date, score, created_at) VALUES
(123456789, CURRENT_DATE - 10, 3, NOW()),
(123456789, CURRENT_DATE - 9,  4, NOW()),
(123456789, CURRENT_DATE - 8,  5, NOW()),
(123456789, CURRENT_DATE - 7,  2, NOW()),
(123456789, CURRENT_DATE - 6,  3, NOW()),
(123456789, CURRENT_DATE - 5,  4, NOW()),
(123456789, CURRENT_DATE - 4,  5, NOW()),
(123456789, CURRENT_DATE - 3,  2, NOW());
\q
```

Теперь в Telegram отправь `/insights` — увидишь корреляции.

---

## 13. Если не работает

### Python: «'python' is not recognized»
- Не поставил галочку «Add to PATH» при установке. Переустанови Python 3.12 с этой галочкой.
- Или временный обход: используй `py -3.12` вместо `python` во всех командах.

### Python: «'py' is not recognized»
- Не установлен Python launcher. Скачай и переустанови Python 3.12 с python.org, на втором экране установщика отметь «py launcher».

### PowerShell: «Activate.ps1 cannot be loaded because running scripts is disabled»
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```
Выполни **в PowerShell от админа** (Win+X → Terminal Admin), затем подтверди `Y`.

### pip: «no matching distribution found for ctranslate2»
У тебя Python 3.13, не 3.12. Проверь:
```powershell
python --version
```
Если 3.13 — удали venv и пересоздай через `py -3.12`:
```powershell
deactivate
Remove-Item -Recurse -Force .venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

### pip: ошибка с Visual C++ при установке psycopg2-binary
Редко на Python 3.12 (есть готовые wheels), но если случилось:
- Скачай и установи **Microsoft C++ Build Tools** с https://visualstudio.microsoft.com/visual-cpp-build-tools/. При установке отметь «Desktop development with C++». Это ~6 ГБ, долго.

### Postgres: служба не запущена
```powershell
Start-Service postgresql-x64-17
```
Если ругается «service not found» — Postgres не установлен или установлен под другим именем; проверь `Get-Service -Name "postgresql*"`.

### Postgres: коннект обрывается (ConnectionResetError / WinError 10054)
Скорее всего, на машине стоит несколько версий Postgres, и они мешают друг другу. Проверь:
```powershell
Get-WmiObject Win32_Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object Name, State, PathName
```
Если служб больше одной — удали лишние через Control Panel → Programs.

### Alembic: «could not connect to server» или `ConnectionRefusedError`
- Проверь, что Postgres запущен: `Get-Service postgresql-x64-17` → `Running`.
- Проверь, что порт правильный: `& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U habitbot -d habitbot -h 127.0.0.1 -p 5432 -c "SHOW port;"`. Если psql отвечает на 5432, а alembic на другой порт — значит, в `.env` или **в переменной среды Windows** `DATABASE_URL` стоит не тот порт. Проверь так:
  ```powershell
  python -c "from src.infrastructure.config import Settings; print(repr(Settings().database_url))"
  $env:DATABASE_URL
  ```
- Если в `$env:DATABASE_URL` есть что-то — это env-переменная перебивает `.env`. Удали её:
  ```powershell
  Remove-Item Env:DATABASE_URL
  [Environment]::SetEnvironmentVariable("DATABASE_URL", $null, "User")
  ```

### Бот не отвечает на сообщения
- Проверь логи в PowerShell — там должно писать про входящие апдейты, если ты что-то отправил боту.
- Убедись, что пишешь именно своему боту (по username из BotFather).
- Перезапусти бота (`Ctrl+C`, потом `python -m src`).
- Если в логах ошибка `Unauthorized` — токен в `.env` неверный или с пробелами.

### Ollama: Connection refused / coach не отвечает
- Ollama не запущена. Запусти ярлык из меню Пуск, дождись иконки в трее.
- Проверь: `curl http://localhost:11434/api/version` должно вернуть JSON.
- Если порт 11434 занят другим приложением — задай переменную `OLLAMA_HOST=http://127.0.0.1:11435` в `.env` и в самой Ollama (через переменную окружения `OLLAMA_HOST`, см. документацию Ollama).

### Ollama: модель не найдена / model 'llama3.1:8b' not found
- Не скачана. Запусти `ollama pull llama3.1:8b` (см. секцию 4.2).
- Проверь список установленных: `ollama list`.

### Ollama: отвечает очень медленно (30+ секунд)
- Модель крутится на CPU. Проверь: `ollama ps` — колонка PROCESSOR должна быть `GPU` (хотя бы частично).
- Если CPU 100% — либо у тебя нет дискретной NVIDIA, либо драйверы устарели. Обнови драйверы или поставь модель полегче: `ollama pull llama3.2:3b` и в `.env` поменяй `OLLAMA_MODEL=llama3.2:3b`.

### Ollama: «out of memory» при первом запросе
Модель не помещается в VRAM/RAM. Переходи на `llama3.2:3b` (нужно 2 ГБ) или закрой другие тяжёлые приложения (Chrome с 50 вкладками легко съедает 8 ГБ).

### Голосовые: модель скачивается бесконечно
- Проверь соединение (модель 480 МБ).
- Папка `C:\Users\<имя>\.cache\huggingface\hub\` должна расти.
- Если совсем плохо с интернетом — поставь `WHISPER_MODEL_SIZE=tiny` в `.env` (модель будет 75 МБ, но качество распознавания плохое — годится только для проверки, что трубопровод работает).

### Хочу удалить всё и начать заново
```powershell
# Остановить бота: Ctrl+C
deactivate
Remove-Item -Recurse -Force .venv
# Очистить БД от данных:
& "C:\Program Files\PostgreSQL\17\bin\psql.exe" -U postgres -h 127.0.0.1 -c "DROP DATABASE habitbot; CREATE DATABASE habitbot OWNER habitbot;"
# Теперь иди в секцию 5
```

### Если совсем ничего не получается на нативном Windows
Переходи на WSL 2:
```powershell
wsl --install -d Ubuntu-22.04
```
В Ubuntu всё ставится без капризов. Команды для Ubuntu есть в общедоступных туториалах по Linux-разработке. На WSL под Windows 11 — нативная производительность.

---

## Что после первого успешного запуска

1. **Зафиксируй свой Telegram user_id** (`/profile`) — он пригодится для исследовательской части диплома (выгрузка истории из `coach_messages` в Jupyter).
2. **Реши, что делать с salt в `CoachingMode.assign()`** (файл `src/domain/value_objects/coaching_mode.py`). Если планируешь тестировать на 5-10 знакомых, и важно, чтобы попало нужное число людей в каждую группу — для исследования это надо чётко зафиксировать в дипломе («использовалась salt='habitbot_v1', дата начала эксперимента такая-то»).
3. **Подключи Jupyter** для анализа: данные из `coach_messages` и `habit_logs` грузишь через pandas (`pd.read_sql`), считаешь retention по группам — это и есть исследовательская часть.
4. **Перед сдачей** — добей покрытие тестов до 70%+. Шаблон `FakeRepo` есть в `tests/unit/application/test_complete_habit.py`. Нужны тесты для `RegisterUserUseCase`, `CreateHabitUseCase`, `GetTodayProgressUseCase`, `ExtractHabitsFromTextUseCase`, `ProcessVoiceMessageUseCase`, `SendRemindersUseCase` — все они сейчас на 0%.

Удачи на защите.
