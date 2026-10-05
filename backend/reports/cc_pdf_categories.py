"""Formal portrait PDF for the «Статистика по категориям» report."""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from reports.cc_chat_metrics import CHANNEL_LABELS

FONT_REGULAR = "ReportTimes"
FONT_BOLD = "ReportTimes-Bold"
_FONTS_READY = False

_ROW_ALT = colors.HexColor("#F4F4F4")
_TOTAL_BG = colors.HexColor("#EAEAEA")
_GRID = colors.HexColor("#7A7A7A")
_RULE = colors.HexColor("#2F2F2F")
_MUTED = colors.HexColor("#555555")

FALLBACK_AUTHOR = "Антонов В.А."


def _looks_like_mock_name(*parts: str) -> bool:
    """Mock AD seeds names like «Dev» / «Role 01» — treat as empty for PDF."""
    joined = " ".join(part.strip() for part in parts if part and part.strip())
    if not joined:
        return True
    lowered = joined.casefold()
    if lowered in {"dev", "test", "user", "admin"}:
        return True
    if lowered.startswith("role ") or " role " in f" {lowered} ":
        return True
    return False


def resolve_author_name(user: Any) -> str:
    """ФИО аналитика, который выгружает отчёт; иначе заглушка."""
    if user is None or not getattr(user, "is_authenticated", False):
        return FALLBACK_AUTHOR
    last = (getattr(user, "last_name", None) or "").strip()
    first = (getattr(user, "first_name", None) or "").strip()
    if last and first and not _looks_like_mock_name(last, first):
        return f"{last} {first}"
    if last and not _looks_like_mock_name(last):
        return last
    if first and not _looks_like_mock_name(first):
        return first
    username = ""
    getter = getattr(user, "get_username", None)
    if callable(getter):
        username = (getter() or "").strip()
    elif getattr(user, "username", ""):
        username = str(user.username).strip()
    if username:
        try:
            from django.db.models import Q

            from online_chat.models import OperatorProfile

            profile = (
                OperatorProfile.objects.filter(is_active=True)
                .filter(Q(external_id=username) | Q(display_name=username))
                .first()
            )
        except Exception:  # noqa: BLE001 — PDF must still render without chat profiles
            profile = None
        display = (profile.display_name or "").strip() if profile else ""
        if display and not _looks_like_mock_name(display):
            return display
    return FALLBACK_AUTHOR


def _register_times_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    pairs = (
        (
            Path("/Library/Fonts/Times New Roman.ttf"),
            Path("/Library/Fonts/Times New Roman Bold.ttf"),
        ),
        (
            Path("/System/Library/Fonts/Supplemental/Times New Roman.ttf"),
            Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman.ttf"),
            Path("/usr/share/fonts/truetype/msttcorefonts/Times_New_Roman_Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSerif-Bold.ttf"),
        ),
        # Docker/slim images typically ship DejaVu, not Times/Liberation.
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
    )
    regular_path: Path | None = None
    bold_path: Path | None = None
    for regular, bold in pairs:
        if regular.is_file():
            regular_path = regular
            bold_path = bold if bold.is_file() else regular
            break
    if regular_path is None:
        raise RuntimeError(
            "Не найден шрифт Times New Roman (или Liberation Serif) для PDF-отчёта"
        )
    pdfmetrics.registerFont(TTFont(FONT_REGULAR, str(regular_path)))
    pdfmetrics.registerFont(TTFont(FONT_BOLD, str(bold_path)))
    _FONTS_READY = True


def _ru_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    text = str(value or "").strip()
    if not text:
        return "—"
    try:
        return date.fromisoformat(text[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return text


def _format_generated_at(value: Any) -> str:
    from django.utils import timezone as dj_tz

    moment: datetime | None = None
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            moment = None
    if moment is None:
        moment = dj_tz.now()
    if dj_tz.is_aware(moment):
        moment = dj_tz.localtime(moment)
    return moment.strftime("%d.%m.%Y %H:%M")


def _fmt_int(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return str(int(round(float(value))))
    except (TypeError, ValueError):
        return str(value)


def _fmt_pct(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):.2f}".replace(".", ",")
    except (TypeError, ValueError):
        return str(value)


def _department_label(department_id: str) -> str:
    if not department_id or department_id in {"all"}:
        return ""
    try:
        from online_chat.models import Department

        department = Department.objects.filter(id=department_id).first()
    except Exception:  # noqa: BLE001
        return department_id
    if department is None:
        return department_id
    return department.name


def _filters_line(filters: dict[str, Any]) -> str:
    parts: list[str] = []
    messenger = str(filters.get("messenger") or "").strip()
    if messenger and messenger not in {"all", "online_chat"}:
        parts.append(CHANNEL_LABELS.get(messenger, messenger))
    department_id = str(filters.get("department_id") or "").strip()
    department = _department_label(department_id)
    if department:
        parts.append(department)
    return ", ".join(parts)


class _NumberedCanvas(pdf_canvas.Canvas):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:  # noqa: N802 — reportlab API
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(page_count)
            super().showPage()
        super().save()

    def _draw_footer(self, page_count: int) -> None:
        width, _height = A4
        y = 12 * mm
        self.setStrokeColor(_RULE)
        self.setLineWidth(0.4)
        self.line(20 * mm, y + 6, width - 20 * mm, y + 6)
        self.setFont(FONT_REGULAR, 9)
        self.setFillColor(_MUTED)
        label = f"Стр. {self._pageNumber} из {page_count}"
        self.drawRightString(width - 20 * mm, y, label)


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "kicker": ParagraphStyle(
            "CategoriesKicker",
            fontName=FONT_REGULAR,
            fontSize=9,
            leading=12,
            textColor=_MUTED,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "title": ParagraphStyle(
            "CategoriesTitle",
            fontName=FONT_BOLD,
            fontSize=16,
            leading=20,
            textColor=colors.black,
            alignment=TA_LEFT,
            spaceAfter=0,
        ),
        "meta_label": ParagraphStyle(
            "CategoriesMetaLabel",
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=_MUTED,
            alignment=TA_LEFT,
        ),
        "meta_value": ParagraphStyle(
            "CategoriesMetaValue",
            fontName=FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=colors.black,
            alignment=TA_LEFT,
        ),
        "th": ParagraphStyle(
            "CategoriesTableHead",
            fontName=FONT_REGULAR,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_LEFT,
        ),
        "th_right": ParagraphStyle(
            "CategoriesTableHeadRight",
            fontName=FONT_REGULAR,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_RIGHT,
        ),
        "td": ParagraphStyle(
            "CategoriesTableCell",
            fontName=FONT_REGULAR,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_LEFT,
        ),
        "td_bold": ParagraphStyle(
            "CategoriesTableCellBold",
            fontName=FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_LEFT,
        ),
        "num": ParagraphStyle(
            "CategoriesTableNum",
            fontName=FONT_REGULAR,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_RIGHT,
        ),
        "num_bold": ParagraphStyle(
            "CategoriesTableNumBold",
            fontName=FONT_BOLD,
            fontSize=11,
            leading=14,
            textColor=colors.black,
            alignment=TA_RIGHT,
        ),
    }


def _meta_rows(payload: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[list[Any]]:
    filters = payload.get("filters") or {}
    summary = payload.get("summary") or {}
    period = f"{_ru_date(filters.get('date_from'))} — {_ru_date(filters.get('date_to'))}"
    closed = summary.get("closed")
    if closed is None:
        rows = payload.get("rows") or []
        total = next((row for row in rows if row.get("is_total")), None)
        closed = (total or {}).get("closed", "")
    pairs = [
        ("Отчётный период", period),
        ("Дата формирования", _format_generated_at(payload.get("generated_at"))),
        ("Сформировал", str(payload.get("generated_by") or FALLBACK_AUTHOR)),
        ("Вид обращений", "Онлайн-чат"),
        ("Закрыто обращений", _fmt_int(closed) or "0"),
    ]
    extra = _filters_line(filters)
    if extra:
        pairs.append(("Фильтры", extra))
    return [
        [
            Paragraph(escape(label), styles["meta_label"]),
            Paragraph(escape(value), styles["meta_value"]),
        ]
        for label, value in pairs
    ]


def _data_table(payload: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> Table:
    columns = payload.get("columns") or [
        {"key": "category", "label": "Категория"},
        {"key": "closed", "label": "Обращений закрыто"},
        {"key": "share_pct", "label": "% от обращений"},
    ]
    header = []
    for index, column in enumerate(columns):
        style = styles["th"] if index == 0 else styles["th_right"]
        header.append(Paragraph(escape(str(column.get("label") or column.get("key") or "")), style))
    data: list[list[Any]] = [header]
    total_index: int | None = None
    for row in payload.get("rows") or []:
        is_total = bool(row.get("is_total")) or str(row.get("category") or "") == "Итого"
        name_style = styles["td_bold"] if is_total else styles["td"]
        num_style = styles["num_bold"] if is_total else styles["num"]
        category = Paragraph(escape(str(row.get("category") or "")), name_style)
        closed = Paragraph(escape(_fmt_int(row.get("closed"))), num_style)
        share = Paragraph(escape(_fmt_pct(row.get("share_pct"))), num_style)
        data.append([category, closed, share])
        if is_total:
            total_index = len(data) - 1
    col_widths = [width * 0.58, width * 0.20, width * 0.22]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    commands: list[tuple[Any, ...]] = [
        ("FONTNAME", (0, 0), (-1, -1), FONT_REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.4, _GRID),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    for index in range(len(data)):
        if index % 2 == 1:
            commands.append(("BACKGROUND", (0, index), (-1, index), _ROW_ALT))
    if total_index is not None:
        commands.extend(
            [
                ("BACKGROUND", (0, total_index), (-1, total_index), _TOTAL_BG),
                ("FONTNAME", (0, total_index), (-1, total_index), FONT_BOLD),
                ("LINEABOVE", (0, total_index), (-1, total_index), 1.1, _RULE),
            ]
        )
    table.setStyle(TableStyle(commands))
    return table


def build_categories_pdf(payload: dict[str, Any]) -> bytes:
    _register_times_fonts()
    styles = _styles()
    buffer = BytesIO()
    left = right = 20 * mm
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=str(payload.get("title") or "Статистика по категориям"),
        author=str(payload.get("generated_by") or FALLBACK_AUTHOR),
    )
    usable = A4[0] - left - right
    meta = Table(
        _meta_rows(payload, styles),
        colWidths=[usable * 0.34, usable * 0.66],
    )
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LINEABOVE", (0, 0), (-1, 0), 0.8, _RULE),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, _RULE),
            ]
        )
    )
    story = [
        Paragraph("ОТЧЁТ", styles["kicker"]),
        Spacer(1, 4),
        Paragraph(escape(str(payload.get("title") or "Статистика по категориям")), styles["title"]),
        Spacer(1, 10),
        meta,
        Spacer(1, 14),
        _data_table(payload, styles, usable),
    ]
    document.build(story, canvasmaker=_NumberedCanvas)
    return buffer.getvalue()
