"""Database aggregations for assistant monitoring and FR-RPT-ASS reports.

Counts, averages and the p95 rank are computed in SQL. The Python loops only
fill calendar buckets that the database did not return.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Any
from zoneinfo import ZoneInfo

from django.db import connection, transaction
from django.db.models import Avg, CharField, Count, Max, Q, QuerySet, Subquery
from django.db.models.functions import TruncDate, TruncHour
from django.db.utils import OperationalError
from django.utils import timezone

from assistant.models import (
    AssistantReportSchedule,
    AssistantReportTemplate,
    AssistantRequestEvent,
)
from assistant.monitoring_errors import (
    AggregationError,
    ExportTooLargeError,
    InvalidPeriodError,
    InvalidQueryError,
    MetricsStoreUnavailable,
    MonitoringError,
    PeriodTooLargeError,
    QueryTimeoutError,
)
from hub.models import AssistantAnswerFeedback


logger = logging.getLogger("assistant.monitoring")

MINSK = ZoneInfo("Europe/Minsk")
MAX_PERIOD_DAYS = 366
DEFAULT_PERIOD_DAYS = 14
PAGE_SIZE_DEFAULT = 50
PAGE_SIZE_MAX = 100
CSV_MAX_ROWS = 50_000
XLSX_MAX_ROWS = 5_000
SLA_MS = 2000.0
HOUR_GRAIN_MAX_DAYS = 31
SAMPLE_LIMIT = 50
TEXT_PREVIEW = 500

QUERY_TYPES = frozenset(item[0] for item in AssistantRequestEvent.QUERY_TYPE_CHOICES)
FEEDBACK_VALUES = frozenset({"useful", "incomplete", "incorrect", "unrated"})
KIND_VALUES = frozenset({"all", "errors", "hallucinations"})
GRAIN_VALUES = frozenset({"day", "hour"})
METRIC_VALUES = frozenset({"usefulness", "relevance", "latency"})
ORDER_FIELDS = {
    "created_at": "created_at",
    "total_ms": "total_ms",
    "top_relevance": "top_relevance",
    "id": "id",
}
TEMPLATE_METRICS = frozenset(
    {
        "requests_total",
        "avg_relevance",
        "feedback_used_pct",
        "p95_latency",
        "error_rate",
        "hallucination_rate",
        "over_sla_pct",
    }
)
EXPORT_FORMATS = frozenset({"csv", "xlsx"})
CADENCES = frozenset(
    item[0] for item in AssistantReportSchedule.CADENCE_CHOICES
)
REPORT_ROW_FR_IDS = (
    "FR-RPT-ASS-01;FR-RPT-ASS-02;FR-RPT-ASS-04"
)

PERIOD_KEYS = frozenset({"date_from", "date_to", "department", "query_type"})
LIST_KEYS = PERIOD_KEYS | frozenset(
    {"page", "page_size", "order", "kind", "feedback"}
)
SERIES_KEYS = PERIOD_KEYS | frozenset({"grain", "metric"})
REPORT_KEYS = PERIOD_KEYS | frozenset({"report_id", "format"})


def _today() -> date:
    return datetime.now(MINSK).date()


def _parse_iso_date(value: str | None, field: str) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise InvalidPeriodError(
            "Дата указывается в формате ГГГГ-ММ-ДД.",
            fields={field: ["Дата указывается в формате ГГГГ-ММ-ДД."]},
        )
    text = value.strip()
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        raise InvalidPeriodError(
            "Дата указывается в формате ГГГГ-ММ-ДД.",
            fields={field: ["Дата указывается в формате ГГГГ-ММ-ДД."]},
        )
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise InvalidPeriodError(
            "Дата указывается в формате ГГГГ-ММ-ДД.",
            fields={field: ["Такой даты не существует."]},
        ) from exc


def _reject_unknown(query: Any, allowed: frozenset[str]) -> None:
    unknown = [key for key in query.keys() if key not in allowed]
    if unknown:
        fields = {
            key: ["Неизвестный параметр."]
            for key in unknown
        }
        raise InvalidQueryError(
            "В запросе есть неизвестные параметры.",
            fields=fields,
        )


def _optional_choice(
    query: Any,
    name: str,
    allowed: frozenset[str],
) -> str:
    raw = query.get(name)
    if raw in (None, ""):
        return ""
    if not isinstance(raw, str):
        raise InvalidQueryError(
            "Некорректное значение фильтра.",
            fields={name: ["Ожидается строка из допустимого списка."]},
        )
    value = raw.strip()
    if not value:
        return ""
    if value not in allowed:
        raise InvalidQueryError(
            "Некорректное значение фильтра.",
            fields={name: [f"Допустимые значения: {', '.join(sorted(allowed))}."]},
        )
    return value


def _department(query: Any) -> str:
    raw = query.get("department")
    if raw in (None, ""):
        return ""
    if not isinstance(raw, str):
        raise InvalidQueryError(
            "Некорректное подразделение.",
            fields={"department": ["Ожидается строка."]},
        )
    value = raw.strip()
    if len(value) > 128:
        raise InvalidQueryError(
            "Некорректное подразделение.",
            fields={"department": ["Не длиннее 128 символов."]},
        )
    return value


def parse_period(query: Any, *, allowed: frozenset[str]) -> dict[str, Any]:
    """Inclusive Minsk calendar period. Stored instants stay in UTC."""
    _reject_unknown(query, allowed)
    today = _today()
    date_from = _parse_iso_date(query.get("date_from"), "date_from")
    date_to = _parse_iso_date(query.get("date_to"), "date_to")
    if date_from is None:
        date_from = today - timedelta(days=DEFAULT_PERIOD_DAYS - 1)
    if date_to is None:
        date_to = today
    if date_from > today or date_to > today:
        raise InvalidPeriodError(
            "Нельзя запрашивать будущие даты.",
            fields={"date_to": ["Конец периода не может быть в будущем."]},
        )
    if date_from > date_to:
        raise InvalidPeriodError(
            "Начало периода позже конца.",
            fields={"date_from": ["Начало не может быть позже конца."]},
        )
    inclusive_days = (date_to - date_from).days + 1
    if inclusive_days > MAX_PERIOD_DAYS:
        raise PeriodTooLargeError()
    start = datetime.combine(date_from, datetime.min.time(), tzinfo=MINSK)
    end = datetime.combine(
        date_to + timedelta(days=1),
        datetime.min.time(),
        tzinfo=MINSK,
    )
    return {
        "date_from": date_from,
        "date_to": date_to,
        "start": start.astimezone(dt_timezone.utc),
        "end": end.astimezone(dt_timezone.utc),
        "department": _department(query),
        "query_type": _optional_choice(query, "query_type", QUERY_TYPES),
    }


def parse_page(query: Any) -> tuple[int, int, list[str]]:
    page = _positive_int(query.get("page"), "page", default=1)
    page_size = _positive_int(
        query.get("page_size"),
        "page_size",
        default=PAGE_SIZE_DEFAULT,
    )
    if page_size > PAGE_SIZE_MAX:
        raise InvalidQueryError(
            "Слишком большой размер страницы.",
            fields={"page_size": [f"Не больше {PAGE_SIZE_MAX}."]},
        )
    return page, page_size, _order_by(query.get("order"))


def _positive_int(raw: Any, field: str, *, default: int) -> int:
    if raw in (None, ""):
        return default
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        value = int(raw.strip())
    else:
        raise InvalidQueryError(
            "Некорректное число.",
            fields={field: ["Ожидается целое число."]},
        )
    if value < 1:
        raise InvalidQueryError(
            "Некорректное число.",
            fields={field: ["Значение должно быть не меньше 1."]},
        )
    return value


def _order_by(raw: Any) -> list[str]:
    if raw in (None, ""):
        return ["-created_at", "-id"]
    if not isinstance(raw, str):
        raise InvalidQueryError(
            "Недопустимое поле сортировки.",
            fields={"order": ["Ожидается имя поля из белого списка."]},
        )
    text = raw.strip()
    descending = text.startswith("-")
    name = text[1:] if descending else text
    column = ORDER_FIELDS.get(name)
    if column is None:
        raise InvalidQueryError(
            "Недопустимое поле сортировки.",
            fields={
                "order": [
                    "Разрешены created_at, total_ms, top_relevance, id."
                ]
            },
        )
    prefix = "-" if descending else ""
    tie = "-id" if descending else "id"
    if column == "id":
        return [f"{prefix}id"]
    return [f"{prefix}{column}", tie]


def base_queryset(filters: dict[str, Any]) -> QuerySet[AssistantRequestEvent]:
    qs = AssistantRequestEvent.objects.filter(
        created_at__gte=filters["start"],
        created_at__lt=filters["end"],
    )
    if filters["department"]:
        qs = qs.filter(department=filters["department"])
    if filters["query_type"]:
        qs = qs.filter(query_type=filters["query_type"])
    return qs


def with_feedback(
    qs: QuerySet[AssistantRequestEvent],
) -> QuerySet[AssistantRequestEvent]:
    choice = (
        AssistantAnswerFeedback.objects.filter(
            message_id=models_outer_message(),
            username=models_outer_username(),
        )
        .exclude(message_id="")
        .values("choice")[:1]
    )
    return qs.annotate(
        feedback_choice=Subquery(choice, output_field=CharField())
    )


def models_outer_message() -> Any:
    from django.db.models import OuterRef

    return OuterRef("message_id")


def models_outer_username() -> Any:
    from django.db.models import OuterRef

    return OuterRef("username")


def _percent(part: int, whole: int) -> float | None:
    if whole <= 0:
        return None
    return round(100.0 * part / whole, 1)


def _guard_store(exc: OperationalError) -> MonitoringError:
    text = str(exc).lower()
    logger.error("monitoring_store_failure error_type=%s", type(exc).__name__)
    if "timeout" in text or "cancel" in text:
        return QueryTimeoutError()
    return MetricsStoreUnavailable()


def run_read(fn: Any) -> Any:
    """Read-only snapshot. A database outage becomes a monitoring error."""
    try:
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL statement_timeout = %s", ["15000"])
            return fn()
    except OperationalError as exc:
        raise _guard_store(exc) from exc
    except MonitoringError:
        raise
    except Exception as exc:
        logger.error(
            "monitoring_aggregation_failed error_type=%s",
            type(exc).__name__,
        )
        raise AggregationError() from exc


def _stats(qs: QuerySet[AssistantRequestEvent]) -> dict[str, Any]:
    annotated = with_feedback(qs)
    totals = annotated.aggregate(
        total=Count("id"),
        useful=Count("id", filter=Q(feedback_choice="useful")),
        incomplete=Count("id", filter=Q(feedback_choice="incomplete")),
        incorrect=Count("id", filter=Q(feedback_choice="incorrect")),
        marked=Count("id", filter=Q(hallucination_marked=True)),
        avg_relevance=Avg("top_relevance"),
        avg_ms=Avg("total_ms"),
        max_ms=Max("total_ms"),
        timed=Count("id", filter=Q(total_ms__isnull=False)),
        over_sla=Count("id", filter=Q(total_ms__gt=SLA_MS)),
    )
    card_incorrect = annotated.filter(
        Q(feedback_choice="incorrect") | Q(outcome=AssistantRequestEvent.OUTCOME_LLM_ERROR)
    ).count()
    totals["card_incorrect"] = card_incorrect
    totals["unrated"] = (
        int(totals["total"] or 0)
        - int(totals["useful"] or 0)
        - int(totals["incomplete"] or 0)
        - int(totals["incorrect"] or 0)
    )
    return totals


def _widget_number(value: float | None, *, message: str, status: str = "ok") -> dict[str, Any]:
    return {
        "status": status,
        "value": value,
        "message": message,
    }


def _safe_widget(name: str, fn: Any) -> dict[str, Any]:
    try:
        with transaction.atomic():
            return fn()
    except OperationalError:
        logger.warning("monitoring_widget_store_unavailable widget=%s", name)
        return {
            "status": "error",
            "value": None,
            "message": "Хранилище метрик временно недоступно.",
        }
    except Exception:
        logger.warning("monitoring_widget_failed widget=%s", name)
        return {
            "status": "error",
            "value": None,
            "message": "Не удалось посчитать показатель.",
        }


def build_summary(filters: dict[str, Any]) -> dict[str, Any]:
    qs = base_queryset(filters)

    def usefulness() -> dict[str, Any]:
        totals = _stats(qs)
        total = int(totals["total"] or 0)
        if total == 0:
            return _widget_number(None, message="Нет данных за период", status="empty")
        return {
            "status": "ok",
            "value": _percent(int(totals["useful"] or 0), total),
            "message": "Доля ответов с отметкой «воспользовался» среди всех ответов.",
            "counts": {
                "total": total,
                "useful": int(totals["useful"] or 0),
                "incomplete": int(totals["incomplete"] or 0),
                "incorrect": int(totals["incorrect"] or 0),
                "unrated": int(totals["unrated"] or 0),
            },
        }

    def incorrect() -> dict[str, Any]:
        totals = _stats(qs)
        total = int(totals["total"] or 0)
        if total == 0:
            return _widget_number(None, message="Нет данных за период", status="empty")
        return {
            "status": "ok",
            "value": _percent(int(totals["card_incorrect"] or 0), total),
            "message": "Оценка «не воспользовался» или сбой модели.",
            "count": int(totals["card_incorrect"] or 0),
        }

    def hallucinations() -> dict[str, Any]:
        totals = _stats(qs)
        total = int(totals["total"] or 0)
        marked = int(totals["marked"] or 0)
        if total == 0:
            return _widget_number(None, message="Нет данных за период", status="empty")
        if marked == 0:
            return _widget_number(None, message="Нет разметки", status="empty")
        return {
            "status": "ok",
            "value": _percent(marked, total),
            "message": "Доля ответов, отмеченных аналитиком как галлюцинация. Цель не выше 3%.",
            "count": marked,
        }

    def latency() -> dict[str, Any]:
        totals = _stats(qs)
        timed = int(totals["timed"] or 0)
        if timed == 0:
            return {
                "status": "empty",
                "value": None,
                "avg_ms": None,
                "max_ms": None,
                "p95_ms": None,
                "over_sla_pct": None,
                "message": "Нет замеров времени ответа.",
            }
        p95 = percentile_total_ms(qs)
        avg_ms = totals["avg_ms"]
        max_ms = totals["max_ms"]
        return {
            "status": "ok",
            "value": None if p95 is None else round(p95, 1),
            "avg_ms": None if avg_ms is None else round(float(avg_ms), 1),
            "max_ms": None if max_ms is None else round(float(max_ms), 1),
            "p95_ms": None if p95 is None else round(float(p95), 1),
            "over_sla_pct": _percent(int(totals["over_sla"] or 0), timed),
            "message": "Порог SLA — 2 секунды.",
        }

    widgets = {
        "usefulness": _safe_widget("usefulness", usefulness),
        "incorrect_answers": _safe_widget("incorrect_answers", incorrect),
        "hallucinations": _safe_widget("hallucinations", hallucinations),
        "latency": _safe_widget("latency", latency),
    }
    return {
        "period": {
            "date_from": filters["date_from"].isoformat(),
            "date_to": filters["date_to"].isoformat(),
            "timezone": "Europe/Minsk",
        },
        "generated_at": timezone.now().isoformat(),
        "department": filters["department"],
        "query_type": filters["query_type"],
        "widgets": widgets,
    }


def percentile_total_ms(qs: QuerySet[AssistantRequestEvent]) -> float | None:
    """Nearest-rank p95: row number ceil(0.95 * n), computed in the database."""
    inner = (
        qs.filter(total_ms__isnull=False)
        .order_by()
        .values("id", "total_ms")
    )
    compiler = inner.query.get_compiler(using=inner.db)
    sql, params = compiler.as_sql()
    wrapped = (
        "SELECT total_ms FROM ("
        " SELECT total_ms,"
        " ROW_NUMBER() OVER (ORDER BY total_ms ASC, id ASC) AS rn,"
        " COUNT(*) OVER () AS cnt"
        f" FROM ({sql}) AS src"
        ") ranked"
        " WHERE rn = ((cnt * 95 + 99) / 100)"
    )
    with connection.cursor() as cursor:
        cursor.execute(wrapped, params)
        row = cursor.fetchone()
    if not row or row[0] is None:
        return None
    return float(row[0])


def _bucket_rows(
    qs: QuerySet[AssistantRequestEvent],
    *,
    grain: str,
) -> list[dict[str, Any]]:
    annotated = with_feedback(qs)
    if grain == "hour":
        annotated = annotated.annotate(bucket=TruncHour("created_at", tzinfo=MINSK))
    else:
        annotated = annotated.annotate(bucket=TruncDate("created_at", tzinfo=MINSK))
    grouped = (
        annotated.values("bucket")
        .annotate(
            sessions=Count("id"),
            useful=Count("id", filter=Q(feedback_choice="useful")),
            incomplete=Count("id", filter=Q(feedback_choice="incomplete")),
            incorrect=Count("id", filter=Q(feedback_choice="incorrect")),
            avg_relevance=Avg("top_relevance"),
            avg_ms=Avg("total_ms"),
            max_ms=Max("total_ms"),
        )
        .order_by("bucket")
    )
    return list(grouped)


def _bucket_key(value: Any, grain: str) -> str:
    if value is None:
        return ""
    if grain == "hour":
        if timezone.is_naive(value):
            value = timezone.make_aware(value, MINSK)
        local = value.astimezone(MINSK).replace(minute=0, second=0, microsecond=0)
        return local.strftime("%Y-%m-%dT%H:%M")
    if isinstance(value, datetime):
        return value.date().isoformat()
    return value.isoformat()


def _point(bucket: str, row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "bucket": bucket,
            "sessions": 0,
            "useful": 0,
            "incomplete": 0,
            "incorrect": 0,
            "unrated": 0,
            "useful_pct": None,
            "avg_relevance": None,
            "avg_ms": None,
            "max_ms": None,
        }
    sessions = int(row["sessions"] or 0)
    useful = int(row["useful"] or 0)
    incomplete = int(row["incomplete"] or 0)
    incorrect = int(row["incorrect"] or 0)
    avg_relevance = row["avg_relevance"]
    avg_ms = row["avg_ms"]
    max_ms = row["max_ms"]
    return {
        "bucket": bucket,
        "sessions": sessions,
        "useful": useful,
        "incomplete": incomplete,
        "incorrect": incorrect,
        "unrated": sessions - useful - incomplete - incorrect,
        "useful_pct": _percent(useful, sessions),
        "avg_relevance": None if avg_relevance is None else round(float(avg_relevance), 1),
        "avg_ms": None if avg_ms is None else round(float(avg_ms), 1),
        "max_ms": None if max_ms is None else round(float(max_ms), 1),
    }


def iter_buckets(filters: dict[str, Any], grain: str) -> list[str]:
    if grain == "hour":
        span = (filters["date_to"] - filters["date_from"]).days + 1
        if span > HOUR_GRAIN_MAX_DAYS:
            raise PeriodTooLargeError(
                "Для группировки по часам период не длиннее 31 дня."
            )
        cursor_at = datetime.combine(
            filters["date_from"],
            datetime.min.time(),
            tzinfo=MINSK,
        )
        end = datetime.combine(
            filters["date_to"] + timedelta(days=1),
            datetime.min.time(),
            tzinfo=MINSK,
        )
        keys: list[str] = []
        while cursor_at < end:
            keys.append(cursor_at.strftime("%Y-%m-%dT%H:%M"))
            cursor_at += timedelta(hours=1)
        return keys
    keys = []
    day = filters["date_from"]
    while day <= filters["date_to"]:
        keys.append(day.isoformat())
        day += timedelta(days=1)
    return keys


def build_series(filters: dict[str, Any], *, grain: str, metric: str) -> dict[str, Any]:
    if grain not in GRAIN_VALUES:
        raise InvalidQueryError(
            "Некорректная группировка.",
            fields={"grain": ["Допустимо day или hour."]},
        )
    if metric not in METRIC_VALUES:
        raise InvalidQueryError(
            "Некорректный показатель ряда.",
            fields={"metric": ["Допустимо usefulness, relevance или latency."]},
        )
    rows = _bucket_rows(base_queryset(filters), grain=grain)
    found = {_bucket_key(row["bucket"], grain): row for row in rows}
    points = [_point(key, found.get(key)) for key in iter_buckets(filters, grain)]
    return {
        "metric": metric,
        "grain": grain,
        "timezone": "Europe/Minsk",
        "period": {
            "date_from": filters["date_from"].isoformat(),
            "date_to": filters["date_to"].isoformat(),
        },
        "points": points,
    }


def _error_population(qs: QuerySet[AssistantRequestEvent]) -> QuerySet[AssistantRequestEvent]:
    annotated = with_feedback(qs)
    return annotated.filter(
        Q(feedback_choice=AssistantAnswerFeedback.CHOICE_INCORRECT)
        | Q(outcome=AssistantRequestEvent.OUTCOME_LLM_ERROR)
        | Q(error_reason=AssistantRequestEvent.REASON_NO_SOURCES)
        | Q(error_reason=AssistantRequestEvent.REASON_LOW_RELEVANCE)
        | Q(error_reason=AssistantRequestEvent.REASON_LLM_ERROR)
    )


def list_events(
    filters: dict[str, Any],
    *,
    page: int,
    page_size: int,
    order: list[str],
    kind: str,
    feedback: str,
) -> dict[str, Any]:
    qs = with_feedback(base_queryset(filters))
    if kind == "errors":
        qs = _error_population(base_queryset(filters))
    elif kind == "hallucinations":
        qs = qs.filter(hallucination_marked=True)
    if feedback == "unrated":
        qs = qs.filter(feedback_choice__isnull=True)
    elif feedback:
        qs = qs.filter(feedback_choice=feedback)
    total = qs.count()
    start = (page - 1) * page_size
    rows = list(qs.order_by(*order)[start : start + page_size])
    include_text = kind in {"errors", "hallucinations"}
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": [_event_public(row, include_text=include_text) for row in rows],
    }


def _event_public(row: AssistantRequestEvent, *, include_text: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.pk,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "department": row.department,
        "username": row.username,
        "query_type": row.query_type,
        "topic": row.topic,
        "outcome": row.outcome,
        "error_reason": row.error_reason,
        "total_ms": row.total_ms,
        "top_relevance": row.top_relevance,
        "doc_count": row.doc_count,
        "feedback": getattr(row, "feedback_choice", None),
        "hallucination_marked": row.hallucination_marked,
    }
    if include_text:
        payload["question_text"] = row.question_text
        payload["answer_text"] = row.answer_text
    return payload


def event_detail(event: AssistantRequestEvent) -> dict[str, Any]:
    annotated = with_feedback(AssistantRequestEvent.objects.filter(pk=event.pk)).first()
    source = annotated or event
    payload = _event_public(source, include_text=True)
    payload.update(
        {
            "request_id": event.request_id,
            "message_id": event.message_id,
            "session_id": event.session_id,
            "ttft_ms": event.ttft_ms,
            "llm_ms": event.llm_ms,
            "token_count": event.token_count,
            "kb_slugs": event.kb_slugs,
            "source_title": event.source_title,
            "hallucination_marked_at": (
                event.hallucination_marked_at.isoformat()
                if event.hallucination_marked_at
                else None
            ),
        }
    )
    return payload


def _grouped_usage_rows(qs: QuerySet[AssistantRequestEvent]) -> list[dict[str, Any]]:
    grouped = (
        with_feedback(qs)
        .annotate(day=TruncDate("created_at", tzinfo=MINSK))
        .values("day", "department", "query_type", "topic")
        .annotate(
            sessions=Count("id"),
            avg_relevance=Avg("top_relevance"),
            useful=Count("id", filter=Q(feedback_choice="useful")),
            incomplete=Count("id", filter=Q(feedback_choice="incomplete")),
            incorrect=Count("id", filter=Q(feedback_choice="incorrect")),
            hallucinations=Count("id", filter=Q(hallucination_marked=True)),
            llm_errors=Count("id", filter=Q(outcome=AssistantRequestEvent.OUTCOME_LLM_ERROR)),
        )
        .order_by("day", "department", "query_type", "topic")
    )
    rows: list[dict[str, Any]] = []
    for item in grouped:
        sessions = int(item["sessions"] or 0)
        avg = item["avg_relevance"]
        avg_percent = None if avg is None else round(float(avg), 1)
        day = item["day"]
        rows.append(
            {
                "date": day.isoformat() if day else "",
                "department": item["department"],
                "query_type": item["query_type"],
                "topic": item["topic"],
                "sessions": sessions,
                "avg_relevance": None if avg_percent is None else round(avg_percent / 100, 3),
                "avg_relevance_percent": avg_percent,
                "useful_pct": _percent(int(item["useful"] or 0), sessions),
                "incomplete_pct": _percent(int(item["incomplete"] or 0), sessions),
                "unused_pct": _percent(int(item["incorrect"] or 0), sessions),
                "incorrect_answers": int(item["incorrect"] or 0) + int(item["llm_errors"] or 0),
                "hallucinations": int(item["hallucinations"] or 0),
                "tool_code": item["query_type"],
                "tool_calls": sessions,
                "fr_ids": REPORT_ROW_FR_IDS,
            }
        )
    return rows


def _relevance_by_type(qs: QuerySet[AssistantRequestEvent]) -> list[dict[str, Any]]:
    grouped = (
        qs.values("query_type")
        .annotate(sessions=Count("id"), avg_relevance=Avg("top_relevance"))
        .order_by("query_type")
    )
    items = []
    for item in grouped:
        avg = item["avg_relevance"]
        items.append(
            {
                "query_type": item["query_type"],
                "sessions": int(item["sessions"] or 0),
                "avg_relevance": None if avg is None else round(float(avg) / 100, 3),
                "avg_relevance_percent": None if avg is None else round(float(avg), 1),
                "fr_id": "FR-RPT-ASS-01",
            }
        )
    return items


def _topics(qs: QuerySet[AssistantRequestEvent]) -> list[dict[str, Any]]:
    grouped = (
        qs.values("topic")
        .annotate(sessions=Count("id"), avg_relevance=Avg("top_relevance"))
        .order_by("-sessions", "topic")
    )
    return [
        {
            "topic": item["topic"],
            "sessions": int(item["sessions"] or 0),
            "avg_relevance_percent": (
                None
                if item["avg_relevance"] is None
                else round(float(item["avg_relevance"]), 1)
            ),
            "fr_id": "FR-RPT-ASS-04",
        }
        for item in grouped
    ]


def _sample(row: AssistantRequestEvent) -> dict[str, Any]:
    created = row.created_at.astimezone(MINSK) if row.created_at else None
    return {
        "id": row.pk,
        "date": created.date().isoformat() if created else "",
        "department": row.department,
        "topic": row.topic,
        "reason": row.error_reason,
        "query_type": row.query_type,
        "question": (row.question_text or "")[:TEXT_PREVIEW],
        "answer": (row.answer_text or "")[:TEXT_PREVIEW],
    }


def build_analytics_payload(filters: dict[str, Any]) -> dict[str, Any]:
    from assistant.ass_reports import FR_RPT_ASS_CATALOG

    qs = base_queryset(filters)
    totals = _stats(qs)
    total = int(totals["total"] or 0)
    rows = _grouped_usage_rows(qs)
    if len(rows) > CSV_MAX_ROWS:
        raise ExportTooLargeError()
    tool_usage_map: dict[str, int] = {}
    for row in rows:
        code = str(row["tool_code"])
        tool_usage_map[code] = tool_usage_map.get(code, 0) + int(row["tool_calls"])
    series = build_series(filters, grain="day", metric="usefulness")
    error_rows = list(_error_population(qs).order_by("-created_at", "-id")[:SAMPLE_LIMIT])
    hallucination_rows = list(
        with_feedback(qs)
        .filter(hallucination_marked=True)
        .order_by("-created_at", "-id")[:SAMPLE_LIMIT]
    )
    schedules = [
        schedule_public(item)
        for item in AssistantReportSchedule.objects.select_related("template").all()
    ]
    templates = [template_public(item) for item in AssistantReportTemplate.objects.all()]
    feedback = {
        "useful_pct": _percent(int(totals["useful"] or 0), total),
        "incomplete_pct": _percent(int(totals["incomplete"] or 0), total),
        "unused_pct": _percent(int(totals["incorrect"] or 0), total),
        "unrated_pct": _percent(int(totals["unrated"] or 0), total),
        "fr_id": "FR-RPT-ASS-02",
    }
    avg = totals["avg_relevance"]
    sections = {
        "FR-RPT-ASS-01": {"relevance_by_type": _relevance_by_type(qs)},
        "FR-RPT-ASS-02": {
            "feedback": feedback,
            "series": series["points"],
        },
        "FR-RPT-ASS-03": {
            "incorrect_answers": _error_population(qs).count(),
            "samples": [_sample(row) for row in error_rows],
        },
        "FR-RPT-ASS-04": {"topics": _topics(qs)},
        "FR-RPT-ASS-05": {
            "hallucinations": int(totals["marked"] or 0),
            "fr_id": "FR-RPT-ASS-05",
            "samples": [_sample(row) for row in hallucination_rows],
        },
        "FR-RPT-ASS-06": {"schedules": schedules},
        "FR-RPT-ASS-07": {
            "charts": ["relevance_trend", "feedback_mix", "latency"],
            "tables": ["usage_rows", "topics"],
            "series": series["points"],
        },
        "FR-RPT-ASS-08": {"templates": templates},
    }
    report_id = filters.get("report_id") or ""
    selected = {report_id: sections[report_id]} if report_id else sections
    return {
        "filters": {
            "date_from": filters["date_from"].isoformat(),
            "date_to": filters["date_to"].isoformat(),
            "department": filters["department"],
            "report_id": report_id,
        },
        "fr_catalog": [dict(item) for item in FR_RPT_ASS_CATALOG],
        "summary": {
            "sessions": total,
            "avg_relevance_percent": None if avg is None else round(float(avg), 1),
            "useful_pct": feedback["useful_pct"],
            "incorrect_answers": int(totals["card_incorrect"] or 0),
            "hallucinations": int(totals["marked"] or 0),
            "tool_calls": total,
        },
        "tool_usage": [
            {"tool_code": code, "calls": calls, "fr_note": "usage / tool calls"}
            for code, calls in sorted(tool_usage_map.items())
        ],
        "rows": rows,
        "sections": selected,
        "stub": False,
        "source": "FR-RPT-ASS · assistant request events",
    }


def parse_report_filters(query: Any) -> dict[str, Any]:
    filters = parse_period(query, allowed=REPORT_KEYS)
    raw_report = query.get("report_id")
    report_id = ""
    if raw_report not in (None, ""):
        if not isinstance(raw_report, str):
            raise InvalidQueryError(
                "Неизвестный отчёт.",
                fields={"report_id": ["Укажите идентификатор FR-RPT-ASS."]},
            )
        report_id = raw_report.strip()
        if report_id:
            from assistant.ass_reports import FR_IDS

            if report_id not in FR_IDS:
                raise InvalidQueryError(
                    "Неизвестный отчёт.",
                    fields={"report_id": ["Укажите идентификатор FR-RPT-ASS."]},
                )
    raw_format = query.get("format")
    if raw_format in (None, ""):
        export_format = "csv"
    elif not isinstance(raw_format, str):
        raise InvalidQueryError(
            "Некорректный формат.",
            fields={"format": ["Допустимо csv или xlsx."]},
        )
    else:
        export_format = raw_format.strip().lower()
        if export_format not in EXPORT_FORMATS:
            raise InvalidQueryError(
                "Некорректный формат.",
                fields={"format": ["Допустимо csv или xlsx."]},
            )
    filters["report_id"] = report_id
    filters["format"] = export_format
    return filters


def template_public(item: AssistantReportTemplate) -> dict[str, Any]:
    return {
        "id": item.pk,
        "name": item.name,
        "metrics": list(item.metrics or []),
        "format": item.export_format,
    }


def schedule_public(item: AssistantReportSchedule) -> dict[str, Any]:
    return {
        "id": item.pk,
        "cadence": item.cadence,
        "report_id": item.report_id,
        "template_id": item.template_id,
        "enabled": item.enabled,
        "last_run_at": item.last_run_at.isoformat() if item.last_run_at else None,
        "last_status": item.last_status,
        "last_error": item.last_error,
        "last_summary": item.last_summary or {},
    }


def validate_template_payload(body: dict[str, Any]) -> dict[str, Any]:
    name = body.get("name")
    if not isinstance(name, str) or not name.strip():
        raise InvalidQueryError(
            "Укажите название шаблона.",
            fields={"name": ["Название обязательно."]},
        )
    if len(name.strip()) > 200:
        raise InvalidQueryError(
            "Слишком длинное название.",
            fields={"name": ["Не длиннее 200 символов."]},
        )
    metrics = body.get("metrics")
    if not isinstance(metrics, list) or not metrics:
        raise InvalidQueryError(
            "Выберите хотя бы одну метрику.",
            fields={"metrics": ["Нужен непустой список метрик из белого списка."]},
        )
    cleaned: list[str] = []
    for metric in metrics:
        if not isinstance(metric, str) or metric not in TEMPLATE_METRICS:
            raise InvalidQueryError(
                "Неизвестная метрика.",
                fields={"metrics": ["Метрика не входит в белый список."]},
            )
        if metric not in cleaned:
            cleaned.append(metric)
    export_format = body.get("format") or AssistantReportTemplate.FORMAT_CSV
    if export_format not in EXPORT_FORMATS:
        raise InvalidQueryError(
            "Некорректный формат.",
            fields={"format": ["Допустимо csv или xlsx."]},
        )
    return {
        "name": name.strip(),
        "metrics": cleaned,
        "export_format": export_format,
    }


def validate_schedule_payload(body: dict[str, Any]) -> dict[str, Any]:
    cadence = body.get("cadence")
    if cadence not in CADENCES:
        raise InvalidQueryError(
            "Некорректная периодичность.",
            fields={"cadence": ["Допустимо daily, weekly или monthly."]},
        )
    report_id = body.get("report_id") or ""
    if report_id:
        from assistant.ass_reports import FR_IDS

        if not isinstance(report_id, str) or report_id not in FR_IDS:
            raise InvalidQueryError(
                "Неизвестный отчёт.",
                fields={"report_id": ["Укажите идентификатор FR-RPT-ASS."]},
            )
    template_id = body.get("template_id")
    if template_id in ("", None):
        template_id = None
    elif isinstance(template_id, bool) or not isinstance(template_id, int):
        raise InvalidQueryError(
            "Некорректный шаблон.",
            fields={"template_id": ["Ожидается числовой идентификатор."]},
        )
    enabled = body.get("enabled", True)
    if not isinstance(enabled, bool):
        raise InvalidQueryError(
            "Некорректный флаг.",
            fields={"enabled": ["Ожидается true или false."]},
        )
    return {
        "cadence": cadence,
        "report_id": report_id,
        "template_id": template_id,
        "enabled": enabled,
    }


def snapshot_for_schedule(schedule: AssistantReportSchedule) -> dict[str, Any]:
    """Counts only. Dialog text is not copied into the schedule snapshot."""
    today = _today()
    if schedule.cadence == AssistantReportSchedule.CADENCE_DAILY:
        date_from = today - timedelta(days=1)
        date_to = date_from
    elif schedule.cadence == AssistantReportSchedule.CADENCE_WEEKLY:
        date_to = today - timedelta(days=1)
        date_from = date_to - timedelta(days=6)
    else:
        first_this_month = today.replace(day=1)
        date_to = first_this_month - timedelta(days=1)
        date_from = date_to.replace(day=1)
    filters = {
        "date_from": date_from,
        "date_to": date_to,
        "start": datetime.combine(date_from, datetime.min.time(), tzinfo=MINSK).astimezone(dt_timezone.utc),
        "end": datetime.combine(
            date_to + timedelta(days=1),
            datetime.min.time(),
            tzinfo=MINSK,
        ).astimezone(dt_timezone.utc),
        "department": "",
        "query_type": "",
        "report_id": schedule.report_id,
    }
    totals = _stats(base_queryset(filters))
    total = int(totals["total"] or 0)
    avg = totals["avg_relevance"]
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "sessions": total,
        "avg_relevance_percent": None if avg is None else round(float(avg), 1),
        "useful_pct": _percent(int(totals["useful"] or 0), total),
        "incorrect_answers": int(totals["card_incorrect"] or 0),
        "hallucinations": int(totals["marked"] or 0),
    }

