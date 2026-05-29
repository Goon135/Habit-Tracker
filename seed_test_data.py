"""Засеивает БД реалистичными тестовыми данными для одного пользователя.

Создаёт пользователя «Алексей» (id=123456789) и набор данных, который позволяет
вручную протестировать почти все функции бота:

- 6 привычек: булевые, количественная, цель с дедлайном, weekdays-расписание,
  одна архивная (для проверки фильтров active_only).
- Логи за последние 60 дней — со стримами 30+, 10+, разнобоем в количественной,
  и одной «свежей» серией пропусков (для burnout-детектора и инсайтов).
- Записи настроения за 30 дней — с корреляцией: меньше выполнено → ниже score.
- Достижения, которые по логике должны быть открыты (streak_3/7/21/30, habits_1/3/5).
- Очки и уровень, посчитанные из тех же формул, что и в gamification.py.
- Несколько сообщений диалога с коучем — чтобы был контекст в /coach.

ЗАПУСК:
    # из корня проекта, после `alembic upgrade head`:
    python scripts/seed_test_data.py

Скрипт идемпотентен: при повторном запуске пользователь и его данные удаляются
и создаются заново. Никаких других пользователей не трогает.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

# Чтобы скрипт работал из любой точки запуска — добавляем корень проекта в sys.path.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, select

from src.infrastructure.config import Settings
from src.infrastructure.database.database import Database
from src.infrastructure.database.models.orm import (
    AchievementModel,
    CoachMessageModel,
    HabitLogModel,
    HabitModel,
    MoodEntryModel,
    UserModel,
)
from src.domain.services.gamification import calculate_points_for_completion


# ───────────────────── Параметры тестового пользователя ─────────────────────

USER_ID = 1580208131
USERNAME = "anton_test"
FIRST_NAME = "Антон"

TODAY = date.today()
REGISTERED_AT = datetime.utcnow() - timedelta(days=60)

# Этот же хэш использует CoachingMode.assign — здесь повторяем формулу один в один,
# чтобы пользователь не «переехал» из группы при первом /start.
_COACHING_SALT = "habitbot_v1"


def _assign_coaching_mode(user_id: int) -> str:
    digest = hashlib.md5(f"{_COACHING_SALT}:{user_id}".encode()).digest()
    return "llm" if digest[0] % 2 == 0 else "template"


# ───────────────────── Утилиты для построения логов ─────────────────────

def _consecutive_days_ending_today(streak_days: int) -> list[date]:
    """Список дат для подряд идущей серии, заканчивающейся сегодня."""
    return [TODAY - timedelta(days=i) for i in range(streak_days)][::-1]


def _weekday_dates_in_range(start: date, end: date, weekdays: set[int]) -> list[date]:
    """Все даты [start, end] с конкретными днями недели (0=Пн..6=Вс)."""
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() in weekdays:
            out.append(cur)
        cur += timedelta(days=1)
    return out


# ───────────────────── Основная сидер-логика ─────────────────────

async def seed(db: Database) -> dict:
    async with db.session() as session:
        # 1. Удаляем всё прошлое за этим user_id, чтобы скрипт был идемпотентным.
        # Порядок важен: сначала зависимые таблицы.
        await session.execute(delete(CoachMessageModel).where(CoachMessageModel.user_id == USER_ID))
        await session.execute(delete(AchievementModel).where(AchievementModel.user_id == USER_ID))
        await session.execute(delete(MoodEntryModel).where(MoodEntryModel.user_id == USER_ID))
        await session.execute(delete(HabitLogModel).where(HabitLogModel.user_id == USER_ID))
        await session.execute(delete(HabitModel).where(HabitModel.user_id == USER_ID))
        await session.execute(delete(UserModel).where(UserModel.id == USER_ID))
        await session.commit()

        # 2. Пользователь. points и level пересчитаем в самом конце,
        #    когда будут известны все completed-логи.
        coaching_mode = _assign_coaching_mode(USER_ID)
        user = UserModel(
            id=USER_ID,
            username=USERNAME,
            first_name=FIRST_NAME,
            points=0,
            level=1,
            reminder_time=time(9, 0),
            coaching_mode=coaching_mode,
            registered_at=REGISTERED_AT,
            motivation_style="competition",  # «упор на серии и рекорды» — подходит к данным
            priority_focus="streak",
            onboarding_completed=True,
            memory_summary=(
                "Алексей бегает каждое утро уже больше месяца — это его флагман. "
                "Чтение идёт волнами, недавно был срыв 4 дня. Любит количественные "
                "цели (вода 3 л/день). Сейчас работает над целью «500 английских слов» "
                "со сроком 60 дней."
            ),
            memory_updated_at=datetime.utcnow() - timedelta(days=2),
        )
        session.add(user)
        await session.flush()

        # 3. Привычки. Сохраняем сразу — нужны id для логов.
        habits_to_add = [
            HabitModel(
                user_id=USER_ID, name="Утренний бег", category="Спорт",
                frequency="daily", is_active=True,
                created_at=REGISTERED_AT,
            ),
            HabitModel(
                user_id=USER_ID, name="Чтение перед сном", category="Обучение",
                frequency="daily", is_active=True,
                created_at=REGISTERED_AT + timedelta(days=2),
            ),
            HabitModel(
                user_id=USER_ID, name="Вода", category="Здоровье",
                frequency="daily", is_active=True,
                target_value=3.0, unit="литр",
                created_at=REGISTERED_AT + timedelta(days=5),
            ),
            HabitModel(
                user_id=USER_ID, name="Зал", category="Спорт",
                # Пн/Ср/Пт (формат: weekdays:0,2,4)
                frequency="weekdays:0,2,4", is_active=True,
                created_at=REGISTERED_AT + timedelta(days=7),
            ),
            HabitModel(
                user_id=USER_ID, name="Выучить 500 английских слов",
                category="Обучение",
                frequency="daily", is_active=True,
                target_value=500.0, unit="слово",
                is_goal=True, end_date=TODAY + timedelta(days=60),
                created_at=REGISTERED_AT + timedelta(days=15),
            ),
            HabitModel(
                user_id=USER_ID, name="Утренний душ", category="Здоровье",
                frequency="daily", is_active=False,  # архивная
                created_at=REGISTERED_AT,
            ),
        ]
        for h in habits_to_add:
            session.add(h)
        await session.flush()  # получаем id

        # Раздаём id обратно по понятным именам.
        run, reading, water, gym, english_goal, _archived_shower = habits_to_add

        # 4. Логи.
        # Логи делаем «по-доменному»: completed=True у тех, кто реально выполнен;
        # у количественных value может быть < target, тогда completed=False.
        # Это нужно, чтобы Streak.calculate (по completed-дням) дал ожидаемые серии.
        logs: list[HabitLogModel] = []
        completed_count = 0  # для подсчёта итоговых очков

        # — Бег: ровно 32 дня подряд до сегодня. Перекроет порог streak_30.
        for d in _consecutive_days_ending_today(32):
            logs.append(HabitLogModel(
                habit_id=run.id, user_id=USER_ID, log_date=d,
                completed=True, value=1.0,
                logged_at=datetime.combine(d, time(7, 30)),
            ))
            completed_count += 1

        # — Чтение: серия 10 дней → срыв 4 дня → новая серия 3 дня (включая сегодня).
        # Итоговый текущий streak = 3.
        reading_start = TODAY - timedelta(days=16)
        # 10 дней подряд начиная с reading_start (дни 0..9)
        for i in range(10):
            d = reading_start + timedelta(days=i)
            logs.append(HabitLogModel(
                habit_id=reading.id, user_id=USER_ID, log_date=d,
                completed=True, value=1.0,
                logged_at=datetime.combine(d, time(22, 30)),
            ))
            completed_count += 1
        # Дни 10..13 — пропуск, логов нет.
        # Дни 14..16 — снова серия 3 дня.
        for i in range(14, 17):
            d = reading_start + timedelta(days=i)
            logs.append(HabitLogModel(
                habit_id=reading.id, user_id=USER_ID, log_date=d,
                completed=True, value=1.0,
                logged_at=datetime.combine(d, time(22, 30)),
            ))
            completed_count += 1

        # — Вода: 25 дней с разными значениями, чтобы прогресс-бары были разными.
        # target=3 л. Из 25 дней: 20 раз ≥3 (completed=True), 5 раз partial.
        water_values_pattern = [
            3.0, 3.2, 3.0, 2.5, 3.0,    # 5 дней: 4 completed, 1 partial
            3.0, 3.0, 1.5, 3.5, 3.0,    # 5: 4 completed, 1 partial
            3.0, 3.0, 3.0, 0.8, 3.0,    # 5: 4 completed, 1 partial
            3.0, 3.0, 3.0, 3.0, 2.0,    # 5: 4 completed, 1 partial
            3.0, 3.0, 3.0, 3.0, 1.8,    # 5: 4 completed, 1 partial
        ]
        water_start = TODAY - timedelta(days=24)
        for i, v in enumerate(water_values_pattern):
            d = water_start + timedelta(days=i)
            done = v >= 3.0
            logs.append(HabitLogModel(
                habit_id=water.id, user_id=USER_ID, log_date=d,
                completed=done, value=v,
                logged_at=datetime.combine(d, time(20, 0)),
            ))
            if done:
                completed_count += 1

        # — Зал: только Пн/Ср/Пт за последние 30 дней.
        gym_days = _weekday_dates_in_range(
            TODAY - timedelta(days=30), TODAY, weekdays={0, 2, 4},
        )
        for d in gym_days:
            logs.append(HabitLogModel(
                habit_id=gym.id, user_id=USER_ID, log_date=d,
                completed=True, value=1.0,
                logged_at=datetime.combine(d, time(19, 0)),
            ))
            completed_count += 1

        # — Цель «английские слова»: накопительный прогресс по 8-12 слов/день.
        # Никогда не достигает 500 за день (это цель на 60 дней), но логи есть —
        # нужно показать, что цели тоже логируются и видны в /export.
        # 14 дней назад начали. completed=False, потому что 8 < 500 за день,
        # но в /today они должны показываться как «привычки с прогрессом».
        english_start = TODAY - timedelta(days=14)
        for i in range(15):
            d = english_start + timedelta(days=i)
            value = 8 + (i % 5)  # 8..12
            logs.append(HabitLogModel(
                habit_id=english_goal.id, user_id=USER_ID, log_date=d,
                completed=False, value=float(value),
                logged_at=datetime.combine(d, time(21, 0)),
            ))

        for lg in logs:
            session.add(lg)

        # 5. Настроение: 30 ежедневных записей. Корреляция с пропусками чтения —
        # в дни срыва (дни 10..13 от reading_start) score ниже среднего.
        mood_start = TODAY - timedelta(days=29)
        reading_slump = {reading_start + timedelta(days=i) for i in range(10, 14)}
        for i in range(30):
            d = mood_start + timedelta(days=i)
            if d in reading_slump:
                score = 2
                note = "Что-то прокрастинирую, чтение забросил"
            elif i % 7 == 0:
                score = 5
                note = "Отличная неделя, всё по плану"
            elif i % 4 == 0:
                score = 4
                note = None
            else:
                score = 3
                note = None
            session.add(MoodEntryModel(
                user_id=USER_ID, entry_date=d, score=score, note=note,
                created_at=datetime.combine(d, time(22, 0)),
            ))

        # 6. Достижения. Выдаём те, что по логике должны быть открыты:
        #    - habits_1, habits_3, habits_5 (у нас 5 активных привычек),
        #    - streak_3, streak_7, streak_21, streak_30 (у бега серия 32).
        # earned_at ставим в день, когда условие реально выполнилось.
        achievements_to_grant = [
            ("habits_1",  "🌱 Первый шаг",         "Создана первая привычка!",  REGISTERED_AT),
            ("habits_3",  "🌿 Тройной фокус",       "Три активные привычки!",     REGISTERED_AT + timedelta(days=7)),
            ("habits_5",  "🌳 Пятёрка лидера",      "Пять активных привычек!",    REGISTERED_AT + timedelta(days=15)),
            ("streak_3",  "🔥 Первый огонь",        "Серия 3 дня подряд!",        datetime.combine(TODAY - timedelta(days=29), time(8, 0))),
            ("streak_7",  "⭐ Недельный марафон",    "Серия 7 дней подряд!",       datetime.combine(TODAY - timedelta(days=25), time(8, 0))),
            ("streak_21", "🏆 21 день — привычка!", "Привычка сформирована!",     datetime.combine(TODAY - timedelta(days=11), time(8, 0))),
            ("streak_30", "💎 Месяц стабильности",  "Серия 30 дней подряд!",      datetime.combine(TODAY - timedelta(days=2), time(8, 0))),
        ]
        for code, title, desc, earned_at in achievements_to_grant:
            session.add(AchievementModel(
                user_id=USER_ID, code=code, title=title,
                description=desc, earned_at=earned_at,
            ))

        # 7. Несколько сообщений диалога с коучем — для контекста в /coach.
        coach_messages = [
            ("user",
             "Привет, я уже месяц бегаю каждое утро. Как закрепить?",
             datetime.utcnow() - timedelta(days=3, hours=2)),
            ("assistant",
             "Месяц подряд — это уже не случайность, это твой новый рекорд! "
             "Чтобы закрепить, попробуй привязать пробежку к существующему "
             "ритуалу (например, сразу после умывания). И поставь себе следующий "
             "ориентир — 60 дней. Твой текущий стрик уже больше 30!",
             datetime.utcnow() - timedelta(days=3, hours=2)),
            ("user",
             "С чтением получается хуже, на прошлой неделе сорвался на 4 дня.",
             datetime.utcnow() - timedelta(days=1, hours=5)),
            ("assistant",
             "Срывы — часть процесса. Главное, что ты вернулся: уже 3 дня подряд снова "
             "читаешь. Это новый старт, не «продолжение неудачи». Хочешь, разберём, "
             "что именно сбило в те 4 дня — поймём триггер и подстелим соломки?",
             datetime.utcnow() - timedelta(days=1, hours=5)),
            ("user",
             "Да, было много работы и поздние ужины. К ночи уже ничего не хотелось.",
             datetime.utcnow() - timedelta(days=1, hours=4, minutes=55)),
            ("assistant",
             "Понятно — в загруженные дни вечернее чтение проигрывает усталости. "
             "Может быть стоит на такие дни заменять 20 минут книги на 5 минут — "
             "это всё равно засчитается в серию и не даст «выпадения». Подойдёт?",
             datetime.utcnow() - timedelta(days=1, hours=4, minutes=54)),
        ]
        for role, content, created_at in coach_messages:
            session.add(CoachMessageModel(
                user_id=USER_ID, role=role, content=content, created_at=created_at,
            ))

        # 8. Пересчитываем очки и уровень.
        # CompleteHabit начисляет за каждое successfull completion:
        # BASE_POINTS (10) + (streak_length // 7) * 2.
        # Восстановить точные очки задним числом сложно (нужно проиграть
        # стрик-историю каждой привычки по дням), поэтому используем
        # консервативную оценку: 10 очков за каждое completed-выполнение
        # плюс умеренный бонус только за активную сейчас серию бега.
        base_points = completed_count * 10
        run_streak_bonus = sum(
            (s_len // 7) * 2 for s_len in range(1, 33)  # день 1..32 бега
        )
        user.points = base_points + run_streak_bonus
        user.level = 1 + user.points // 100

        await session.commit()

        # Возвращаем сводку для логов.
        result = await session.execute(select(HabitModel).where(HabitModel.user_id == USER_ID))
        habits_count = len(result.scalars().all())
        result = await session.execute(select(HabitLogModel).where(HabitLogModel.user_id == USER_ID))
        logs_count = len(result.scalars().all())

    return {
        "user_id": USER_ID,
        "username": USERNAME,
        "first_name": FIRST_NAME,
        "coaching_mode": coaching_mode,
        "habits": habits_count,
        "logs": logs_count,
        "points": user.points,
        "level": user.level,
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    settings = Settings()
    db = Database(settings.database_url)
    try:
        summary = await seed(db)
        print("\n=== Тестовые данные засеяны ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
        print(
            "\nВ Telegram: пришли боту /start с аккаунта, у которого user_id == "
            f"{USER_ID}, либо подмени user_id в коде на свой.\n"
        )
    finally:
        await db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
