"""CSV / XLSX / PDF export of a selected online-chat report template."""

from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from reports.cc_analytics import build_csv_export, build_xlsx_export, export_filename


def _columns(payload: dict[str, Any]) -> list[dict[str, str]]:
    columns = payload.get("columns") or []
    if columns:
        return [{"key": str(item.get("key") or ""), "label": str(item.get("label") or item.get("key") or "")} for item in columns]
    rows = payload.get("rows") or []
    if not rows:
        return []
    keys = [key for key in rows[0].keys() if key not in {"is_total", "is_section"}]
    return [{"key": key, "label": key} for key in keys]


def _title(payload: dict[str, Any]) -> str:
    return str(payload.get("title") or (payload.get("report") or {}).get("label") or "Отчёт")


def _period(payload: dict[str, Any]) -> str:
    filters = payload.get("filters") or {}
    return f"{filters.get('date_from', '')} — {filters.get('date_to', '')}".strip(" —")


def _cell(row: dict[str, Any], key: str) -> str:
    value = row.get(key, "")
    if value is None:
        return ""
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _sheet_rows(payload: dict[str, Any]) -> list[list[str]]:
    columns = _columns(payload)
    title = _title(payload)
    period = _period(payload)
    rows: list[list[str]] = [[title], [period], [item["label"] for item in columns]]
    for row in payload.get("rows") or []:
        rows.append([_cell(row, item["key"]) for item in columns])
    return rows


def export_report_csv(payload: dict[str, Any]) -> bytes:
    columns = _columns(payload)
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow([_title(payload)])
    writer.writerow([_period(payload)])
    writer.writerow([item["label"] for item in columns])
    for row in payload.get("rows") or []:
        writer.writerow([_cell(row, item["key"]) for item in columns])
    return buffer.getvalue().encode("utf-8")


def _col_letter(index: int) -> str:
    result = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _sheet_xml(rows: list[list[str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        lines.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row):
            cell_ref = f"{_col_letter(c_idx)}{r_idx}"
            safe = escape(value)
            lines.append(f'<c r="{cell_ref}" t="inlineStr"><is><t>{safe}</t></is></c>')
        lines.append("</row>")
    lines.extend(["</sheetData>", "</worksheet>"])
    return "\n".join(lines)


def export_report_xlsx(payload: dict[str, Any]) -> bytes:
    sheet_name = (_title(payload)[:31] or "Report").replace("/", "-")
    sheet_rows = _sheet_rows(payload)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
    workbook = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/>
  </sheets>
</workbook>
"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>
"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(sheet_rows))
    return buffer.getvalue()


def _find_cyrillic_font() -> str | None:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode MS.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    return None


def export_report_pdf(payload: dict[str, Any]) -> bytes:
    report_id = str(
        (payload.get("filters") or {}).get("report")
        or (payload.get("report") or {}).get("id")
        or ""
    ).strip()
    if report_id in {"chat-topics", "chat-categories"}:
        from reports.cc_pdf_categories import build_categories_pdf

        return build_categories_pdf(payload)
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        from reports.cc_pdf import build_pdf_export

        return build_pdf_export(
            {
                "filters": payload.get("filters") or {},
                "source": payload.get("source") or "",
                "summary": payload.get("summary") or {},
                "rows": payload.get("rows") or [],
            },
            title=_title(payload),
        )

    font_name = "Helvetica"
    font_path = _find_cyrillic_font()
    if font_path:
        pdfmetrics.registerFont(TTFont("ReportCyr", font_path))
        font_name = "ReportCyr"

    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    heading = styles["Heading1"]
    heading.fontName = font_name
    heading.fontSize = 12
    heading.leading = 14
    normal = styles["Normal"]
    normal.fontName = font_name
    normal.fontSize = 8
    table_data = _sheet_rows(payload)
    story = [
        Paragraph(escape(_title(payload)), heading),
        Spacer(1, 6),
        Paragraph(escape(_period(payload)), normal),
        Spacer(1, 10),
    ]
    if table_data:
        table = Table(table_data[2:] if len(table_data) > 2 else table_data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), font_name),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F2EC")),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#B7C9BE")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(table)
    document.build(story)
    return buffer.getvalue()


def report_export_filename(payload: dict[str, Any], export_format: str) -> str:
    filters = payload.get("filters") or {}
    report_id = filters.get("report") or (payload.get("report") or {}).get("id") or "report"
    date_from = filters.get("date_from") or "from"
    date_to = filters.get("date_to") or "to"
    return f"{report_id}_{date_from}_{date_to}.{export_format}"


def legacy_export(analytics: dict[str, Any], export_format: str) -> tuple[bytes, str, str]:
    """Keep the generic analytics export for callers that omit `report`."""
    if export_format == "xlsx":
        payload = build_xlsx_export(analytics)
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif export_format == "pdf":
        from reports.cc_pdf import build_pdf_export

        payload = build_pdf_export(analytics)
        content_type = "application/pdf"
    else:
        payload = build_csv_export(analytics)
        content_type = "text/csv; charset=utf-8"
    return payload, content_type, export_filename(analytics.get("filters") or {}, export_format)
