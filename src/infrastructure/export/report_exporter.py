"""Экспорт отчётов за период в CSV и PDF.

PDF делаем через ReportLab — это самый зрелый чистый python-вариант, без внешних
бинарей вроде wkhtmltopdf.
"""
from __future__ import annotations

import csv
import io
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
import os
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from src.domain.repositories.habit_repository import HabitLogRepository, HabitRepository
from src.domain.repositories.other_repositories import MoodRepository
from src.domain.repositories.user_repository import UserRepository
from src.domain.value_objects.streak import Streak


# Шрифт для PDF с кириллицей. Стандартный Helvetica в ReportLab не содержит
# кириллических глифов, поэтому без явной регистрации текст рендерится как
# квадратики (.notdef). Стратегия по приоритету:
# 1. DejaVu, лежащий в репозитории рядом с модулем (`fonts/`). Кросс-платформенно
#    и воспроизводимо: работает одинаково на Windows, Linux, macOS и в Docker.
# 2. Системные шрифты (Linux: DejaVu, Windows: Arial/Segoe UI, macOS: Arial).
# 3. Helvetica — последний шанс не упасть, кириллицы не будет.
#
# Регистрируем семейство Regular + Bold отдельной парой через registerFontFamily,
# чтобы стиль `Title` и тег `<b>` использовали именно жирный вариант, а не
# фолбэкались на Helvetica-Bold (опять без кириллицы).
_BUNDLED_FONTS_DIR = Path(__file__).parent / "fonts"
_FONT_FAMILY = "AppFont"
_FONT_REGISTERED = False


def _try_register_pair(regular_path: str, bold_path: str | None) -> bool:
    """Зарегистрировать Regular (+ опционально Bold) под именем _FONT_FAMILY.

    Возвращает True при успехе. Bold необязателен — если файла нет, заголовки
    просто будут не жирными, но останутся читаемыми.
    """
    try:
        pdfmetrics.registerFont(TTFont(_FONT_FAMILY, regular_path))
    except Exception:
        return False
    bold_name = _FONT_FAMILY  # fallback: bold == regular
    if bold_path and os.path.exists(bold_path):
        try:
            bold_name = f"{_FONT_FAMILY}-Bold"
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        except Exception:
            bold_name = _FONT_FAMILY
    pdfmetrics.registerFontFamily(
        _FONT_FAMILY,
        normal=_FONT_FAMILY,
        bold=bold_name,
        italic=_FONT_FAMILY,
        boldItalic=bold_name,
    )
    return True


def _ensure_font() -> str:
    """Зарегистрировать шрифт один раз за процесс и вернуть его имя.

    Имя возвращается строкой, потому что ReportLab оперирует именами шрифтов,
    а не объектами.
    """
    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _FONT_FAMILY

    # 1. Bundled — основной путь.
    bundled_regular = _BUNDLED_FONTS_DIR / "DejaVuSans.ttf"
    bundled_bold = _BUNDLED_FONTS_DIR / "DejaVuSans-Bold.ttf"
    if bundled_regular.exists():
        if _try_register_pair(str(bundled_regular), str(bundled_bold)):
            _FONT_REGISTERED = True
            return _FONT_FAMILY

    # 2. Системные шрифты. Пары (regular, bold). Bold может отсутствовать.
    system_candidates: list[tuple[str, str | None]] = [
        # Linux
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/TTF/DejaVuSans.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"),
        # Windows
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        (r"C:\Windows\Fonts\tahoma.ttf", r"C:\Windows\Fonts\tahomabd.ttf"),
        # macOS
        ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
    ]
    for regular, bold in system_candidates:
        if os.path.exists(regular):
            if _try_register_pair(regular, bold):
                _FONT_REGISTERED = True
                return _FONT_FAMILY

    # 3. Полный фолбэк — Helvetica. Кириллицы не будет, но не упадём.
    return "Helvetica"


class ReportExporterImpl:
    def __init__(
        self,
        users: UserRepository,
        habits: HabitRepository,
        habit_logs: HabitLogRepository,
        moods: MoodRepository,
    ) -> None:
        self._users = users
        self._habits = habits
        self._logs = habit_logs
        self._moods = moods

    async def export_csv(self, user_id: int, days: int) -> io.BytesIO:
        rows = await self._build_rows(user_id, days)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["Дата", "Привычка", "Категория", "Выполнено", "Настроение"])
        for r in rows:
            writer.writerow(r)
        out = io.BytesIO(buf.getvalue().encode("utf-8-sig"))  # BOM для Excel
        out.seek(0)
        return out

    async def export_pdf(self, user_id: int, days: int) -> io.BytesIO:
        font = _ensure_font()
        user = await self._users.get(user_id)
        habits = await self._habits.list_for_user(user_id, active_only=False)
        today = date.today()

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=A4,
            leftMargin=2 * cm, rightMargin=2 * cm,
            topMargin=2 * cm, bottomMargin=2 * cm,
        )
        styles = getSampleStyleSheet()
        # Применяем шрифт ко всем стандартным стилям, чтобы кириллица рендерилась.
        # Для заголовков используем жирный вариант (зарегистрирован как family).
        bold_name = f"{font}-Bold" if font == _FONT_FAMILY else font
        bold_styles = {"Title", "Heading1", "Heading2", "Heading3",
                       "Heading4", "Heading5", "Heading6"}
        for st in styles.byName.values():
            st.fontName = bold_name if st.name in bold_styles else font

        story = []
        title = user.first_name or "Пользователь"
        story.append(Paragraph(f"Отчёт привычек: {title}", styles["Title"]))
        story.append(Paragraph(
            f"Период: последние {days} дней (до {today.isoformat()})", styles["Normal"]
        ))
        story.append(Spacer(1, 0.5 * cm))

        # Сводная таблица: привычка | серия | выполнено за период
        summary_data = [["Привычка", "Категория", "Серия (дн.)", f"Выполнено / {days}"]]
        since = today - timedelta(days=days - 1)
        for h in habits:
            completed_dates = await self._logs.list_completed_dates(h.id)
            streak = Streak.calculate(completed_dates, today)
            in_window = sum(1 for d in completed_dates if d >= since)
            summary_data.append([h.name, h.category.value, str(streak.length), str(in_window)])

        table = Table(summary_data, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#34495e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), bold_name),       # шапка — жирная
            ("FONTNAME", (0, 1), (-1, -1), font),           # данные — обычный
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ]))
        story.append(table)

        doc.build(story)
        buf.seek(0)
        return buf

    async def _build_rows(self, user_id: int, days: int) -> list[list[str]]:
        today = date.today()
        since = today - timedelta(days=days - 1)
        habits = await self._habits.list_for_user(user_id, active_only=False)
        moods = await self._moods.list_for_user(user_id, since)
        mood_by_date = {m.entry_date: m.score for m in moods}

        rows: list[list[str]] = []
        for h in habits:
            logs = await self._logs.list_for_habit(h.id, since)
            done_by_date = {log.log_date: log.completed for log in logs}
            for i in range(days):
                d = since + timedelta(days=i)
                rows.append([
                    d.isoformat(),
                    h.name,
                    h.category.value,
                    "1" if done_by_date.get(d, False) else "0",
                    str(mood_by_date.get(d, "")),
                ])
        return rows
