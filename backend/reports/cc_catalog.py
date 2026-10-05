"""Ready-made report catalogue for II.6 FR-RPT-CC (online-chat production data)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from reports.cc_analytics import CHANNEL_ONLINE_CHAT, CcAnalyticsError, parse_analytics_filters
from reports.cc_chat_metrics import (
    builder_metric_value,
    report_chat_history,
    report_chat_ratings,
    report_chat_sla,
    report_chat_topics,
    report_correctness,
    report_errors,
    report_executive,
    report_performance,
    report_relevance,
    report_repeats,
    report_usefulness,
)
from reports.cc_chat_sample_reports import (
    report_chat_categories,
    report_chat_dates_offline,
    report_chat_dates_online,
    report_chat_dept_offline,
    report_chat_dept_online,
    report_chat_hours_offline,
    report_chat_hours_online,
    report_chat_missed,
    report_chat_operators_daily,
    report_chat_operators_summary,
    report_chat_time_usage,
)

VISIBLE_REPORT_TYPES = (
    {
        "id": "chat-topics",
        "fr": "FR-RPT-CC-13",
        "label": "Статистика по категориям",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-dept-online",
        "fr": "FR-RPT-CC-11",
        "label": "По отделам (онлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-dept-offline",
        "fr": "FR-RPT-CC-11",
        "label": "По отделам (офлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-period",
        "fr": "FR-RPT-CC-11",
        "label": "По датам (онлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-dates-offline",
        "fr": "FR-RPT-CC-11",
        "label": "По датам (офлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-hours-online",
        "fr": "FR-RPT-CC-11",
        "label": "По часам (онлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-hours-offline",
        "fr": "FR-RPT-CC-11",
        "label": "По часам (офлайн)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-operators",
        "fr": "FR-RPT-CC-05",
        "label": "По операторам",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-operators-summary",
        "fr": "FR-RPT-CC-05",
        "label": "Суммарный по операторам",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-offline",
        "fr": "FR-RPT-CC-12",
        "label": "По пропущенным",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-time-usage",
        "fr": "FR-RPT-CC-05",
        "label": "По времени",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
)

HIDDEN_REPORT_TYPES = (
    {
        "id": "chat-sla",
        "fr": "FR-RPT-CC-03",
        "label": "SLA и время ожидания",
        "default_view": "bar",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat-ratings",
        "fr": "FR-RPT-CC-11",
        "label": "Оценки клиентов",
        "default_view": "pie",
        "group": "Онлайн-чат",
    },
    {
        "id": "chat_history",
        "fr": "FR-RPT-CC-15",
        "label": "Диалоги онлайн-чата (реестр)",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "usefulness",
        "fr": "FR-RPT-CC-08",
        "label": "Полезность подсказок суфлёра",
        "description": "Фильтр периода. Pie: Воспользовался / Неполный / Не воспользовался. Таблица — разрез онлайн-чат / телефония.",
        "default_view": "pie",
        "group": "Суфлёр / LLM",
    },
    {
        "id": "relevance",
        "fr": "FR-RPT-CC-07",
        "label": "Релевантность по каналам и тематикам",
        "description": "Круговая: доли подсказок с высокой / средней / низкой релевантностью. Таблица — канал и тематика закрытия.",
        "default_view": "pie",
        "group": "Суфлёр / LLM",
    },
    {
        "id": "correctness",
        "fr": "FR-RPT-CC-04",
        "label": "Корректность: отметки оператора",
        "default_view": "pie",
        "group": "Суфлёр / LLM",
    },
    {
        "id": "performance",
        "fr": "FR-RPT-CC-05",
        "label": "Производительность (время ответа, AHT)",
        "default_view": "bar",
        "group": "Производительность",
    },
    {
        "id": "errors",
        "fr": "FR-RPT-CC-09",
        "label": "Неиспользованные подсказки",
        "default_view": "table",
        "group": "Суфлёр / LLM",
    },
    {
        "id": "topics",
        "fr": "FR-RPT-CC-13",
        "label": "Закономерности по тематике",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "repeats",
        "fr": "FR-RPT-CC-12",
        "label": "Повторные обращения",
        "default_view": "table",
        "group": "Онлайн-чат",
    },
    {
        "id": "executive",
        "fr": "FR-RPT-CC-11",
        "label": "Сводка для руководства",
        "default_view": "table",
        "group": "Сводные",
    },
)

REPORT_TYPES = VISIBLE_REPORT_TYPES + HIDDEN_REPORT_TYPES

SUFLER_REPORT_IDS = frozenset({"usefulness", "relevance", "errors"})

_REPORT_ALIASES = {
    "rpt-08": "usefulness",
    "rpt-02": "relevance",
    "rpt-07": "relevance",
    "rpt-04": "usefulness",
    "correctness": "usefulness",
    "rpt-05": "performance",
    "rpt-09": "errors",
    "rpt-13": "topics",
    "rpt-12": "repeats",
    "rpt-11": "executive",
    "rpt-10": "executive",
    "chat-categories": "chat-topics",
    "chat-dates-online": "chat-period",
    "chat-missed": "chat-offline",
}

_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "chat-topics": report_chat_categories,
    "chat-dept-online": report_chat_dept_online,
    "chat-dept-offline": report_chat_dept_offline,
    "chat-period": report_chat_dates_online,
    "chat-dates-offline": report_chat_dates_offline,
    "chat-hours-online": report_chat_hours_online,
    "chat-hours-offline": report_chat_hours_offline,
    "chat-operators": report_chat_operators_daily,
    "chat-operators-summary": report_chat_operators_summary,
    "chat-offline": report_chat_missed,
    "chat-time-usage": report_chat_time_usage,
    "chat-sla": report_chat_sla,
    "chat-ratings": report_chat_ratings,
    "chat_history": report_chat_history,
    "usefulness": report_usefulness,
    "relevance": report_relevance,
    "correctness": report_correctness,
    "performance": report_performance,
    "errors": report_errors,
    "topics": report_chat_topics,
    "repeats": report_repeats,
    "executive": report_executive,
}


def _scope(query: Any) -> str:
    value = str(query.get("scope") or "").strip().lower()
    return value if value in {"sufler", "chat"} else ""


def _catalog_for_scope(scope: str) -> list[dict[str, Any]]:
    if scope == "sufler":
        return [item for item in REPORT_TYPES if item["id"] in SUFLER_REPORT_IDS]
    return list(REPORT_TYPES)


def _parse_filters(query: Any) -> dict[str, Any]:
    filters = parse_analytics_filters(query)
    scope = _scope(query)
    default_report = "usefulness" if scope == "sufler" else "chat-topics"
    report_id = (query.get("report") or default_report).strip()
    known = {item["id"] for item in REPORT_TYPES}
    if report_id not in known:
        report_id = _REPORT_ALIASES.get(report_id, default_report)
    if scope == "sufler" and report_id not in SUFLER_REPORT_IDS:
        report_id = "usefulness"
    filters["report"] = report_id
    filters["scope"] = scope
    requested_channel = str(query.get("channel") or "").strip()
    messenger = filters.get("messenger") or ""
    channel = filters.get("channel") or ("" if scope == "sufler" else CHANNEL_ONLINE_CHAT)
    if channel in {"all", "*"}:
        channel = ""
    if scope == "sufler":
        messenger = ""
        # Hub «Статистика суфлёра» omits channel on purpose (phone + chat).
        # parse_analytics_filters would otherwise default to online_chat and hide
        # telephony marks such as «Не воспользовался».
        if not requested_channel or requested_channel in {"all", "*"}:
            channel = ""
        elif requested_channel not in {CHANNEL_ONLINE_CHAT, "telephony", "chat"}:
            channel = ""
        elif requested_channel == "chat":
            channel = CHANNEL_ONLINE_CHAT
        else:
            channel = requested_channel
    elif channel not in {CHANNEL_ONLINE_CHAT, "", "telephony"}:
        messenger = channel
    topic = str(query.get("topic") or "").strip()
    status = str(query.get("status") or query.get("dialogue_status") or "").strip()
    department = str(query.get("department") or "").strip()
    filters["messenger"] = messenger
    filters["channel"] = channel
    filters["topic"] = topic
    filters["status"] = status
    filters["department_id"] = department
    group_by = str(query.get("group_by") or "channel").strip().lower()
    if group_by not in {"", "none", "channel", "topic"}:
        group_by = "channel"
    filters["group_by"] = group_by or "channel"
    return filters


def build_report_payload(query: Any) -> dict[str, Any]:
    filters = _parse_filters(query)
    date_from = date.fromisoformat(filters["date_from"])
    date_to = date.fromisoformat(filters["date_to"])
    report_id = filters["report"]
    meta = next(item for item in REPORT_TYPES if item["id"] == report_id)
    builder = _BUILDERS[report_id]
    scope = filters.get("scope") or ""
    kwargs = {
        "messenger": filters.get("messenger") or "",
        "department_id": filters.get("department_id") or "",
        "topic": filters.get("topic") or "",
        "status": filters.get("status") or "",
    }
    # group_by applies only to relevance report; other builders reject unknown kwargs.
    if report_id == "relevance":
        kwargs["group_by"] = filters.get("group_by") or "channel"
    if report_id in SUFLER_REPORT_IDS:
        kwargs["channel"] = filters.get("channel") or ""
        kwargs["scope"] = scope
    try:
        built = builder(date_from, date_to, **kwargs)
    except TypeError as exc:
        raise CcAnalyticsError(
            f"Не удалось построить отчёт «{meta.get('label') or report_id}»: {exc}"
        ) from exc
    rows = built.get("rows") or []
    chart = built.get("chart") or []
    summary = {
        "report_id": report_id,
        "rows": len(rows),
        "period": f"{filters['date_from']} — {filters['date_to']}",
        **(built.get("summary") or {}),
    }
    # Hide technical ids / advanced percentiles from KPI strip.
    summary.pop("p95_first_response_sec", None)
    summary.pop("p95_ms", None)
    return {
        "filters": filters,
        "catalog": _catalog_for_scope(scope) if scope == "sufler" else list(VISIBLE_REPORT_TYPES),
        "report": meta,
        "rows": rows,
        "columns": built.get("columns") or [],
        "title": built.get("title") or meta.get("label") or report_id,
        "chart": chart,
        "summary": summary,
        "stub": bool(built.get("stub")),
        "source": "Суфлёр" if scope == "sufler" else "Онлайн-чат",
        "alerts": [],
    }


def list_builder_templates(*, saved: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "templates": [
            {
                "id": "tpl-chat-topics-week",
                "name": "Статистика по категориям за неделю",
                "metrics": ["topics_top", "dialogs_closed", "dialogs_total"],
                "filters": {"channel": "online_chat", "period": "week", "report": "chat-topics"},
                "view_mode": "table",
            },
            {
                "id": "tpl-chat-period-week",
                "name": "По датам (онлайн) за неделю",
                "metrics": ["dialogs_total", "dialogs_closed", "avg_first_response_sec"],
                "filters": {"channel": "online_chat", "period": "week", "report": "chat-period"},
                "view_mode": "table",
            },
            {
                "id": "tpl-chat-operators-week",
                "name": "По операторам за неделю",
                "metrics": ["dialogs_total", "aht_sec", "avg_first_response_sec", "sla_pct"],
                "filters": {"channel": "online_chat", "period": "week", "report": "chat-operators"},
                "view_mode": "table",
            },
            {
                "id": "tpl-chat-operators-summary-month",
                "name": "Суммарный по операторам за месяц",
                "metrics": ["dialogs_total", "aht_sec", "csat"],
                "filters": {"channel": "online_chat", "period": "month", "report": "chat-operators-summary"},
                "view_mode": "table",
            },
            {
                "id": "tpl-chat-offline-week",
                "name": "По пропущенным за неделю",
                "metrics": ["dialogs_total", "dialogs_closed", "avg_first_response_sec"],
                "filters": {"channel": "online_chat", "period": "week", "report": "chat-offline"},
                "view_mode": "table",
            },
            {
                "id": "tpl-chat-time-week",
                "name": "По времени за неделю",
                "metrics": ["dialogs_total", "aht_sec"],
                "filters": {"channel": "online_chat", "period": "week", "report": "chat-time-usage"},
                "view_mode": "table",
            },
        ],
        "saved": saved or [],
        "metric_catalog": [
            {"id": "dialogs_total", "label": "Число диалогов"},
            {"id": "dialogs_closed", "label": "Закрытых диалогов"},
            {"id": "sla_pct", "label": "Соблюдение SLA первого ответа, %"},
            {"id": "csat", "label": "Средняя оценка клиента"},
            {"id": "useful_pct", "label": "Полезность суфлёра, %"},
            {"id": "sufler_used_pct", "label": "Использование суфлёра, %"},
            {"id": "relevance_avg", "label": "Средняя релевантность, %"},
            {"id": "incorrect_llm", "label": "Доля «не использовал», %"},
            {"id": "avg_first_response_sec", "label": "Среднее время первого ответа, с"},
            {"id": "topics_top", "label": "Число тематик"},
            {"id": "aht_sec", "label": "Среднее время обработки, с"},
            {"id": "aht", "label": "Среднее время обработки, с"},
        ],
        "stub": False,
    }


def preview_builder(body: dict[str, Any]) -> dict[str, Any]:
    metrics = body.get("metrics") or ["dialogs_total", "useful_pct", "csat"]
    view_mode = body.get("view_mode") or "table"
    name = body.get("name") or "Черновик отчёта"
    today = datetime.now(timezone.utc).date()
    date_from = today - timedelta(days=6)
    date_to = today
    raw_from = body.get("date_from")
    raw_to = body.get("date_to")
    if raw_from:
        try:
            date_from = date.fromisoformat(str(raw_from)[:10])
        except ValueError:
            pass
    if raw_to:
        try:
            date_to = date.fromisoformat(str(raw_to)[:10])
        except ValueError:
            pass

    rows = []
    chart = []
    metric_labels = {
        "dialogs_total": "Число диалогов",
        "dialogs_closed": "Закрытых диалогов",
        "sla_pct": "Соблюдение SLA первого ответа, %",
        "csat": "Средняя оценка клиента",
        "useful_pct": "Полезность суфлёра, %",
        "sufler_used_pct": "Использование суфлёра, %",
        "relevance_avg": "Средняя релевантность, %",
        "incorrect_llm": "Доля «не использовал», %",
        "avg_first_response_sec": "Среднее время первого ответа, с",
        "topics_top": "Число тематик",
        "aht_sec": "Среднее время обработки, с",
        "aht": "Среднее время обработки, с",
    }
    for metric in metrics:
        metric_id = str(metric)
        value, unit = builder_metric_value(metric_id, date_from, date_to)
        label = metric_labels.get(metric_id, metric_id)
        display = value if value is not None else "—"
        rows.append(
            {
                "metric": label,
                "metric_id": metric_id,
                "value": display if not isinstance(display, str) else 0,
                "unit": unit or "—",
                "display": display,
            }
        )
        if isinstance(value, (int, float)):
            chart.append({"label": label, "value": float(value)})
    return {
        "name": name,
        "view_mode": view_mode,
        "rows": [
            {
                "metric": row["metric"],
                "value": row["value"] if isinstance(row["value"], (int, float)) else 0,
                "unit": row["unit"],
            }
            for row in rows
        ],
        "chart": chart,
        "stub": False,
        "message": f"Предпросмотр за период {date_from.isoformat()} — {date_to.isoformat()}.",
        "period": {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
    }
