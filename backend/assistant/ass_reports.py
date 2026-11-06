"""Assistant analytics and export for FR-RPT-ASS / III.10.2."""

from __future__ import annotations

import csv
import io
import zipfile
from typing import Any
from xml.sax.saxutils import escape

EXPORT_CSV = "csv"
EXPORT_XLSX = "xlsx"
EXPORT_FORMATS = frozenset({EXPORT_CSV, EXPORT_XLSX})

# Mapped to III.10.2 / §5.4 (IDs FR-RPT-ASS-*; TZ table mislabels as FR-RPT-CC).
FR_RPT_ASS_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "FR-RPT-ASS-01",
        "title": "Средняя релевантность по типам запросов",
        "description": "Средняя релевантность с разбивкой по типам запросов",
        "tt": "5.4.1.1",
        "acceptance": "ASS-T-RPT-01",
    },
    {
        "id": "FR-RPT-ASS-02",
        "title": "Полезность ответов",
        "description": "Воспользовался / не воспользовался / неполный",
        "tt": "5.4.1.2",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-03",
        "title": "Ошибочные ответы",
        "description": "Список некорректных ответов для QA",
        "tt": "5.4.1.3",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-04",
        "title": "Категоризация по темам",
        "description": "Отчёт по тематикам обращений",
        "tt": "5.4.2.1",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-05",
        "title": "Галлюцинации (RBAC ИБ)",
        "description": "Панель мониторинга галлюцинаций",
        "tt": "5.4.2.2",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-06",
        "title": "Регулярные и ad-hoc отчёты",
        "description": "Расписание и разовые выгрузки",
        "tt": "5.4.3",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-07",
        "title": "Таблицы и графики",
        "description": "Визуализация и выгрузка pdf/xlsx",
        "tt": "5.4.4",
        "acceptance": "ASS-T-14",
    },
    {
        "id": "FR-RPT-ASS-08",
        "title": "Конструктор отчётов",
        "description": "Метрики, формат и шаблоны",
        "tt": "5.4.5",
        "acceptance": "ASS-T-RPT-02",
    },
)

FR_IDS = frozenset(item["id"] for item in FR_RPT_ASS_CATALOG)


def parse_report_filters(query: Any) -> dict[str, Any]:
    """Kept for callers that imported the parser from this module."""
    from assistant.monitoring_query import parse_report_filters as parse_filters

    return parse_filters(query)


def catalog() -> dict[str, Any]:
    return {
        "module": "assistant",
        "section": "III.10.2",
        "consumer_role": "ai_assistant_analyst",
        "permission": "assistant.reports.view",
        "items": [dict(item) for item in FR_RPT_ASS_CATALOG],
    }


def build_analytics(filters: dict[str, Any]) -> dict[str, Any]:
    from assistant.monitoring_query import build_analytics_payload

    return build_analytics_payload(filters)


_EXPORT_HEADERS = [
    "date",
    "department",
    "query_type",
    "topic",
    "sessions",
    "avg_relevance_percent",
    "useful_pct",
    "incomplete_pct",
    "unused_pct",
    "incorrect_answers",
    "hallucinations",
    "tool_code",
    "tool_calls",
    "fr_ids",
]


def iter_csv_chunks(analytics: dict[str, Any]) -> Any:
    """Yield CSV text in small pieces so a long export is not one string."""
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_HEADERS, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    for row in analytics["rows"]:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(row)
        yield buffer.getvalue()


def build_csv_export(analytics: dict[str, Any]) -> bytes:
    return "".join(iter_csv_chunks(analytics)).encode("utf-8")


def _sheet_xml(rows: list[list[str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        lines.append(f'<row r="{r_idx}">')
        for c_idx, value in enumerate(row):
            col = chr(ord("A") + c_idx)
            cell_ref = f"{col}{r_idx}"
            safe = escape(value)
            lines.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{safe}</t></is></c>'
            )
        lines.append("</row>")
    lines.extend(["</sheetData>", "</worksheet>"])
    return "\n".join(lines)


def build_xlsx_export(analytics: dict[str, Any]) -> bytes:
    sheet_rows = [[header for header in _EXPORT_HEADERS]]
    for row in analytics["rows"]:
        sheet_rows.append(
            [
                "" if row.get(header) is None else str(row.get(header, ""))
                for header in _EXPORT_HEADERS
            ]
        )

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
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>
    <sheet name="ASS analytics" sheetId="1" r:id="rId1"/>
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


def export_filename(filters: dict[str, Any], export_format: str) -> str:
    report = filters.get("report_id") or "all"
    dept = filters.get("department") or "all"
    return (
        f"ass-analytics_{filters['date_from']}_{filters['date_to']}"
        f"_{dept}_{report}.{export_format}"
    )
