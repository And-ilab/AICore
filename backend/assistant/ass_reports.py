"""Assistant analytics and export for FR-RPT-ASS / III.10.2."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
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

QUERY_TYPES = ("faq", "procedure", "policy", "hr", "it", "other")
TOPICS = ("отпуска", "переводы", "карты", "доступ", "регламенты")
TOOL_CODES = ("rag_kb", "generate_document", "rpa", "sql_code", "translate", "summarize")


class AssReportsError(ValueError):
    """Invalid assistant report request."""


def _parse_date(value: str | None, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise AssReportsError(f"{field} must be YYYY-MM-DD") from exc


def parse_report_filters(query: Any) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    date_from = _parse_date(query.get("date_from"), "date_from") or (
        today - timedelta(days=13)
    )
    date_to = _parse_date(query.get("date_to"), "date_to") or today
    if date_from > date_to:
        raise AssReportsError("date_from must be <= date_to")

    department = (query.get("department") or "").strip()
    report_id = (query.get("report_id") or "").strip()
    if report_id and report_id not in FR_IDS:
        raise AssReportsError(
            "report_id must be one of: " + ", ".join(sorted(FR_IDS))
        )

    export_format = (query.get("format") or EXPORT_CSV).strip().lower()
    if export_format not in EXPORT_FORMATS:
        raise AssReportsError("format must be csv|xlsx")

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "department": department,
        "report_id": report_id,
        "format": export_format,
    }


def catalog() -> dict[str, Any]:
    return {
        "module": "assistant",
        "section": "III.10.2",
        "consumer_role": "ai_assistant_analyst",
        "permission": "assistant.reports.view",
        "items": [dict(item) for item in FR_RPT_ASS_CATALOG],
    }


def _seed_usage_rows(date_from: date, date_to: date, department: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = date_from
    index = 0
    depts = (department,) if department else ("hr", "it", "retail", "security")
    while day <= date_to:
        for dept in depts:
            qtype = QUERY_TYPES[index % len(QUERY_TYPES)]
            topic = TOPICS[index % len(TOPICS)]
            sessions = 20 + (index % 15)
            avg_rel = round(0.72 + (index % 12) * 0.02, 3)
            useful = 55 + (index % 20)
            incomplete = 15 + (index % 8)
            unused = max(0, 100 - useful - incomplete)
            errors = 1 + (index % 4)
            hallucinations = index % 3
            tool = TOOL_CODES[index % len(TOOL_CODES)]
            tool_calls = 5 + (index % 10)
            rows.append(
                {
                    "date": day.isoformat(),
                    "department": dept,
                    "query_type": qtype,
                    "topic": topic,
                    "sessions": sessions,
                    "avg_relevance": avg_rel,
                    "avg_relevance_percent": int(round(avg_rel * 100)),
                    "useful_pct": useful,
                    "incomplete_pct": incomplete,
                    "unused_pct": unused,
                    "incorrect_answers": errors,
                    "hallucinations": hallucinations,
                    "tool_code": tool,
                    "tool_calls": tool_calls,
                    "fr_ids": "FR-RPT-ASS-01;FR-RPT-ASS-02;FR-RPT-ASS-04",
                }
            )
            index += 1
        day += timedelta(days=1)
    return rows


def build_analytics(filters: dict[str, Any]) -> dict[str, Any]:
    date_from = date.fromisoformat(filters["date_from"])
    date_to = date.fromisoformat(filters["date_to"])
    rows = _seed_usage_rows(date_from, date_to, filters["department"])
    total_sessions = sum(row["sessions"] for row in rows) or 1

    by_query_type: dict[str, dict[str, float]] = {}
    for row in rows:
        bucket = by_query_type.setdefault(
            row["query_type"],
            {"sessions": 0.0, "relevance_sum": 0.0},
        )
        bucket["sessions"] += row["sessions"]
        bucket["relevance_sum"] += row["avg_relevance"] * row["sessions"]

    relevance_by_type = [
        {
            "query_type": qtype,
            "sessions": int(data["sessions"]),
            "avg_relevance": round(data["relevance_sum"] / data["sessions"], 3),
            "avg_relevance_percent": int(
                round(100 * data["relevance_sum"] / data["sessions"])
            ),
            "fr_id": "FR-RPT-ASS-01",
        }
        for qtype, data in sorted(by_query_type.items())
    ]

    feedback = {
        "useful_pct": round(
            sum(row["useful_pct"] * row["sessions"] for row in rows)
            / total_sessions,
            1,
        ),
        "incomplete_pct": round(
            sum(row["incomplete_pct"] * row["sessions"] for row in rows)
            / total_sessions,
            1,
        ),
        "unused_pct": round(
            sum(row["unused_pct"] * row["sessions"] for row in rows)
            / total_sessions,
            1,
        ),
        "fr_id": "FR-RPT-ASS-02",
    }

    tool_usage: dict[str, int] = {}
    for row in rows:
        tool_usage[row["tool_code"]] = (
            tool_usage.get(row["tool_code"], 0) + row["tool_calls"]
        )

    topics: dict[str, int] = {}
    for row in rows:
        topics[row["topic"]] = topics.get(row["topic"], 0) + row["sessions"]

    report_id = filters.get("report_id") or ""
    sections = {
        "FR-RPT-ASS-01": {"relevance_by_type": relevance_by_type},
        "FR-RPT-ASS-02": {"feedback": feedback},
        "FR-RPT-ASS-03": {
            "incorrect_answers": sum(row["incorrect_answers"] for row in rows),
            "samples": [
                {
                    "date": row["date"],
                    "department": row["department"],
                    "topic": row["topic"],
                    "count": row["incorrect_answers"],
                }
                for row in rows
                if row["incorrect_answers"] > 2
            ][:20],
        },
        "FR-RPT-ASS-04": {
            "topics": [
                {"topic": topic, "sessions": count, "fr_id": "FR-RPT-ASS-04"}
                for topic, count in sorted(
                    topics.items(), key=lambda item: (-item[1], item[0])
                )
            ]
        },
        "FR-RPT-ASS-05": {
            "hallucinations": sum(row["hallucinations"] for row in rows),
            "fr_id": "FR-RPT-ASS-05",
        },
        "FR-RPT-ASS-06": {
            "schedules": [
                {"cadence": "daily", "report_id": "FR-RPT-ASS-01", "enabled": True},
                {"cadence": "weekly", "report_id": "FR-RPT-ASS-02", "enabled": True},
                {"cadence": "ad-hoc", "report_id": "FR-RPT-ASS-08", "enabled": True},
            ]
        },
        "FR-RPT-ASS-07": {
            "charts": ["relevance_trend", "feedback_mix", "tool_calls"],
            "tables": ["usage_rows", "topics"],
        },
        "FR-RPT-ASS-08": {
            "templates": [
                {
                    "id": "tpl-relevance",
                    "name": "Релевантность за период",
                    "metrics": ["avg_relevance", "sessions"],
                    "format": "xlsx",
                },
                {
                    "id": "tpl-feedback-tools",
                    "name": "Полезность и tool calls",
                    "metrics": ["useful_pct", "tool_calls"],
                    "format": "csv",
                },
            ]
        },
    }

    selected_sections = (
        {report_id: sections[report_id]}
        if report_id
        else sections
    )

    return {
        "filters": {
            "date_from": filters["date_from"],
            "date_to": filters["date_to"],
            "department": filters["department"],
            "report_id": report_id,
        },
        "fr_catalog": [dict(item) for item in FR_RPT_ASS_CATALOG],
        "summary": {
            "sessions": sum(row["sessions"] for row in rows),
            "avg_relevance_percent": round(
                sum(row["avg_relevance"] * row["sessions"] for row in rows)
                * 100
                / total_sessions,
                1,
            ),
            "useful_pct": feedback["useful_pct"],
            "incorrect_answers": sum(row["incorrect_answers"] for row in rows),
            "hallucinations": sum(row["hallucinations"] for row in rows),
            "tool_calls": sum(row["tool_calls"] for row in rows),
        },
        "tool_usage": [
            {"tool_code": code, "calls": calls, "fr_note": "usage / tool calls"}
            for code, calls in sorted(tool_usage.items())
        ],
        "rows": rows,
        "sections": selected_sections,
        "stub": True,
        "source": "FR-RPT-ASS · III.10.2 stub analytics",
    }


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


def build_csv_export(analytics: dict[str, Any]) -> bytes:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.DictWriter(buffer, fieldnames=_EXPORT_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in analytics["rows"]:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


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
        sheet_rows.append([str(row.get(header, "")) for header in _EXPORT_HEADERS])

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
