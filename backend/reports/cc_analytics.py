"""CC analytics and export for FR-RPT-CC / II.6 (online-chat production path)."""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any
from xml.sax.saxutils import escape

from reports.cc_chat_metrics import build_analytics_rows

CHANNEL_ALL = ""
CHANNEL_TELEPHONY = "telephony"
CHANNEL_ONLINE_CHAT = "online_chat"
CHANNELS = frozenset({CHANNEL_TELEPHONY, CHANNEL_ONLINE_CHAT})

EXPORT_CSV = "csv"
EXPORT_XLSX = "xlsx"
EXPORT_PDF = "pdf"
EXPORT_FORMATS = frozenset({EXPORT_CSV, EXPORT_XLSX, EXPORT_PDF})


class CcAnalyticsError(ValueError):
    """Invalid analytics filter or export request."""


def _parse_date(value: str | None, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise CcAnalyticsError(f"{field} must be YYYY-MM-DD") from exc


def parse_analytics_filters(query: Any) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    date_from = _parse_date(query.get("date_from"), "date_from") or (
        today - timedelta(days=13)
    )
    date_to = _parse_date(query.get("date_to"), "date_to") or today
    if date_from > date_to:
        raise CcAnalyticsError("date_from must be <= date_to")

    # Default to online_chat: telephony is out of current delivery scope.
    raw_channel = query.get("channel")
    if raw_channel is None:
        channel = CHANNEL_ONLINE_CHAT
    else:
        channel = str(raw_channel).strip()
    if channel in {"all", "*"}:
        channel = CHANNEL_ALL
    if channel and channel not in CHANNELS:
        # Allow messenger codes from UI (widget/telegram/…) → treat as chat.
        if channel in {
            "widget",
            "telegram",
            "viber",
            "vk",
            "ok",
            "api",
            "email",
            "phone",
        }:
            messenger = "" if channel == "phone" else channel
            if channel == "phone":
                channel = CHANNEL_TELEPHONY
            else:
                channel = CHANNEL_ONLINE_CHAT
            return {
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "channel": channel,
                "messenger": messenger,
                "format": _parse_format(query),
            }
        raise CcAnalyticsError("channel must be telephony|online_chat|messenger")

    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "channel": channel,
        "messenger": str(query.get("messenger") or "").strip(),
        "format": _parse_format(query),
    }


def _parse_format(query: Any) -> str:
    export_format = (query.get("format") or EXPORT_CSV).strip().lower()
    if export_format not in EXPORT_FORMATS:
        raise CcAnalyticsError("format must be csv|xlsx|pdf")
    return export_format


def _telephony_stub_rows(date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Keep telephony API shape for future; not used for online-chat prod path."""
    rows: list[dict[str, Any]] = []
    day = date_from
    index = 0
    while day <= date_to:
        recognized = 88 + (index % 8)
        useful = 62 + (index % 12)
        incomplete = 18 + (index % 5)
        unused = max(0, 100 - useful - incomplete)
        rows.append(
            {
                "date": day.isoformat(),
                "channel": CHANNEL_TELEPHONY,
                "operator": "—",
                "sessions": 0,
                "recognized_pct": recognized,
                "avg_confidence": round(0.78 + (index % 10) * 0.015, 3),
                "useful_pct": useful,
                "incomplete_pct": incomplete,
                "unused_pct": unused,
                "incorrect_llm": 0,
                "hint_latency_p95_ms": 420 + (index % 9) * 15,
                "aht_sec": 210 + (index % 7) * 12,
            }
        )
        index += 1
        day += timedelta(days=1)
    return rows


def _asr_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_date.setdefault(row["date"], []).append(row)
    series: list[dict[str, Any]] = []
    for day, group in sorted(by_date.items()):
        sessions = sum(item["sessions"] for item in group) or 1
        recognized = round(
            sum(item["recognized_pct"] * item["sessions"] for item in group) / sessions,
            1,
        )
        confidence = round(
            sum(item["avg_confidence"] * item["sessions"] for item in group) / sessions,
            3,
        )
        series.append(
            {
                "date": day,
                "recognized_pct": recognized,
                "avg_confidence": confidence,
                "sessions": sum(item["sessions"] for item in group),
            }
        )
    return series


def build_analytics(filters: dict[str, Any]) -> dict[str, Any]:
    date_from = date.fromisoformat(filters["date_from"])
    date_to = date.fromisoformat(filters["date_to"])
    channel = filters.get("channel") or CHANNEL_ONLINE_CHAT
    messenger = filters.get("messenger") or ""

    if channel == CHANNEL_TELEPHONY:
        rows = _telephony_stub_rows(date_from, date_to)
        summary = {
            "sessions": 0,
            "recognized_pct": 0,
            "avg_confidence": 0,
            "useful_pct": 0,
            "incorrect_llm": 0,
            "hint_latency_p95_ms": 0,
        }
        return {
            "filters": {
                "date_from": filters["date_from"],
                "date_to": filters["date_to"],
                "channel": channel,
            },
            "summary": summary,
            "rows": rows,
            "usefulness": [],
            "asr_quality": _asr_series(rows),
            "stub": True,
            "source": "Телефония",
        }

    rows, summary = build_analytics_rows(
        date_from, date_to, messenger=messenger
    )
    usefulness = [
        {
            "channel": CHANNEL_ONLINE_CHAT,
            "label": "Онлайн-чат",
            "useful_pct": summary.get("useful_pct") or 0,
            "incomplete_pct": 0,
            "unused_pct": 0,
            "sessions": summary.get("sufler_total") or summary.get("sessions") or 0,
        }
    ]
    if summary.get("sufler_total"):
        # Fill incomplete/unused from daily averages when available.
        if rows:
            sessions = sum(r["sessions"] for r in rows) or 1
            usefulness[0]["incomplete_pct"] = round(
                sum(r["incomplete_pct"] * r["sessions"] for r in rows) / sessions, 1
            )
            usefulness[0]["unused_pct"] = round(
                sum(r["unused_pct"] * r["sessions"] for r in rows) / sessions, 1
            )

    return {
        "filters": {
            "date_from": filters["date_from"],
            "date_to": filters["date_to"],
            "channel": CHANNEL_ONLINE_CHAT if channel in {CHANNEL_ALL, ""} else channel,
            "messenger": messenger,
        },
        "summary": {
            "sessions": summary.get("sessions") or 0,
            "recognized_pct": summary.get("recognized_pct") or 0,
            "avg_confidence": summary.get("avg_confidence") or 0,
            "useful_pct": summary.get("useful_pct") or 0,
            "incorrect_llm": summary.get("incorrect_llm") or 0,
            "hint_latency_p95_ms": summary.get("hint_latency_p95_ms") or 0,
            "closed": summary.get("closed"),
            "avg_first_response_sec": summary.get("avg_first_response_sec"),
            "avg_aht_sec": summary.get("avg_aht_sec"),
            "avg_rating": summary.get("avg_rating"),
            "sla_ok_pct": summary.get("sla_ok_pct"),
            "sufler_total": summary.get("sufler_total"),
            "sufler_avg_relevance": summary.get("sufler_avg_relevance"),
        },
        "rows": rows,
        "usefulness": usefulness,
        "asr_quality": [],  # telephony/ASR out of scope
        "stub": not bool(rows),
        "source": "Онлайн-чат",
    }


_EXPORT_HEADERS = [
    "date",
    "channel",
    "operator",
    "sessions",
    "recognized_pct",
    "avg_confidence",
    "useful_pct",
    "incomplete_pct",
    "unused_pct",
    "incorrect_llm",
    "hint_latency_p95_ms",
    "aht_sec",
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
    <sheet name="CC analytics" sheetId="1" r:id="rId1"/>
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
    channel = filters.get("channel") or "online_chat"
    return (
        f"cc-analytics_{filters['date_from']}_{filters['date_to']}"
        f"_{channel}.{export_format}"
    )
