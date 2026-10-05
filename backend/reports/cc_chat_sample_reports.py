"""Online-chat report builders matching the customer Excel sample templates."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable

from django.db.models import Q
from django.utils import timezone as dj_tz

from reports.cc_chat_metrics import dialogs_in_period, first_response_seconds

FIRST_VISIT_LOOKBACK_DAYS = 30
ANSWER_BUCKETS_SEC = (10, 20, 30, 40)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if dj_tz.is_naive(value):
        return dj_tz.make_aware(value, timezone.utc)
    return value


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start, end


def _period_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    start, _ = _day_bounds(date_from)
    _, end = _day_bounds(date_to)
    return start, end


def _is_offline(dialog: Any) -> bool:
    return (dialog.outcome or "") == "offline"


def _split_online_offline(dialogs: list[Any]) -> tuple[list[Any], list[Any]]:
    online = [item for item in dialogs if not _is_offline(item)]
    offline = [item for item in dialogs if _is_offline(item)]
    return online, offline


def _hms(seconds: float | None) -> str:
    if seconds is None:
        return "0:00:00"
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _avg(values: Iterable[float | None]) -> float | None:
    cleaned = [float(item) for item in values if item is not None]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def _fmt_pct(part: float, whole: float) -> float:
    if not whole:
        return 0.0
    return round(100.0 * part / whole, 4)


def _date_label(day: date) -> str:
    return day.strftime("%d.%m.%Y")


def _hour_label(hour: int) -> str:
    return f"{hour:02d} - {hour + 1:02d}"


def _dept_name(dialog: Any) -> str:
    department = getattr(dialog, "department", None)
    if department is not None and getattr(department, "name", ""):
        return department.name
    return "Без отдела"


def _category_name(dialog: Any) -> str:
    node = getattr(dialog, "close_topic_node", None)
    if node is not None:
        path = (node.full_path or node.label or "").strip()
        if path:
            return path.split("/")[0].strip() or path
    topic = (getattr(dialog, "close_topic", None) or "").strip()
    return topic or "Без категории"


def _payload(
    *,
    title: str,
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    chart: list[dict[str, Any]] | None = None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "columns": columns,
        "rows": rows,
        "chart": chart or [],
        "summary": summary or {},
        "stub": False,
    }


def _closed(dialog: Any) -> bool:
    return dialog.status == "closed"


def _missed(dialog: Any) -> bool:
    return (dialog.outcome or "") == "lost"


def _rejected(dialog: Any) -> bool:
    return (dialog.outcome or "") == "rejected"


def _invitation_ignored(dialog: Any) -> bool:
    return (
        getattr(dialog, "initiated_by", "") == "operator"
        and dialog.status == "closed"
        and not dialog.first_response_at
        and (dialog.outcome or "") in {"lost", "rejected", ""}
    )


def _load_messages(dialogs: list[Any]) -> dict[Any, list[Any]]:
    from online_chat.models import DialogMessage

    if not dialogs:
        return {}
    ids = [item.id for item in dialogs]
    grouped: dict[Any, list[Any]] = defaultdict(list)
    for message in DialogMessage.objects.filter(dialog_id__in=ids).order_by("created_at"):
        grouped[message.dialog_id].append(message)
    return grouped


def _count_messages(messages: list[Any], speaker: str) -> int:
    return sum(1 for item in messages if item.speaker == speaker and not item.is_deleted)


def _first_time_ids(dialogs: list[Any], date_from: date) -> set[Any]:
    from online_chat.models import Dialog

    ids: set[Any] = set()
    lookback = date_from - timedelta(days=FIRST_VISIT_LOOKBACK_DAYS)
    known = {
        (item.client_external_id or "").strip()
        for item in dialogs
        if (item.client_external_id or "").strip()
    }
    prior = set()
    if known:
        prior = set(
            Dialog.objects.filter(
                created_at__date__gte=lookback,
                created_at__date__lt=date_from,
                client_external_id__in=known,
            ).values_list("client_external_id", flat=True)
        )
    seen: set[str] = set()
    for dialog in sorted(dialogs, key=lambda item: item.created_at):
        key = (dialog.client_external_id or "").strip()
        if not key:
            ids.add(dialog.id)
            continue
        if key in prior or key in seen:
            continue
        seen.add(key)
        ids.add(dialog.id)
    return ids


def _queue_seconds(dialog: Any) -> float | None:
    end = dialog.accepted_at or dialog.closed_at
    if end is None:
        return None
    return max(0.0, (end - dialog.created_at).total_seconds())


def _personal_queue_seconds(dialog: Any) -> float | None:
    if not dialog.accepted_at or not dialog.first_response_at:
        return None
    return max(0.0, (dialog.first_response_at - dialog.accepted_at).total_seconds())


def _reply_gaps(messages: list[Any]) -> list[float]:
    gaps: list[float] = []
    last_client: datetime | None = None
    for message in messages:
        if message.is_deleted:
            continue
        if message.speaker == "client":
            last_client = message.created_at
        elif message.speaker == "operator" and last_client is not None:
            gaps.append(max(0.0, (message.created_at - last_client).total_seconds()))
            last_client = None
    return gaps


def _answered_within(dialog: Any, seconds: int) -> bool:
    frt = first_response_seconds(dialog)
    return frt is not None and frt <= seconds


def _max_operators_online(start: datetime, end: datetime) -> int:
    from django.db.utils import OperationalError, ProgrammingError
    from online_chat.models import OperatorPresenceLog, OperatorProfile

    try:
        logs = list(
            OperatorPresenceLog.objects.filter(
                presence=OperatorProfile.Presence.ONLINE,
                started_at__lt=end,
            ).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=start))
        )
    except (OperationalError, ProgrammingError):
        return 0
    if logs:
        operators = {str(item.operator_id) for item in logs}
        return len(operators)
    return 0


def _events_by_dialog(dialogs: list[Any]) -> dict[Any, list[Any]]:
    from online_chat.models import DialogEvent

    if not dialogs:
        return {}
    grouped: dict[Any, list[Any]] = defaultdict(list)
    for event in DialogEvent.objects.filter(dialog_id__in=[item.id for item in dialogs]):
        grouped[event.dialog_id].append(event)
    return grouped


def _rating_text(ratings: list[int]) -> str:
    if not ratings:
        return "—"
    avg = sum(ratings) / len(ratings)
    hist: dict[int, int] = defaultdict(int)
    for value in ratings:
        hist[value] += 1
    parts = ", ".join(f"{star}=>{hist[star]} шт." for star in sorted(hist))
    return f"{avg:.2f} (Кол-во оценок: {len(ratings)}) ({parts})"


def _online_metric_row(
    *,
    label: str,
    group: list[Any],
    messages_map: dict[Any, list[Any]],
    first_time: set[Any],
    start: datetime,
    end: datetime,
    is_total: bool = False,
) -> dict[str, Any]:
    op_msgs = sum(_count_messages(messages_map.get(item.id, []), "operator") for item in group)
    cl_msgs = sum(_count_messages(messages_map.get(item.id, []), "client") for item in group)
    queue = _avg(_queue_seconds(item) for item in group)
    personal = _avg(_personal_queue_seconds(item) for item in group)
    missed = [item for item in group if _missed(item)]
    missed_wait = _avg(_queue_seconds(item) for item in missed)
    gaps: list[float] = []
    for item in group:
        gaps.extend(_reply_gaps(messages_map.get(item.id, [])))
    reply = _avg(gaps)
    active_dialogs = [
        item
        for item in group
        if item.first_response_at or item.accepted_at or item.status in {"active", "closed"}
    ]
    answered_20 = sum(1 for item in group if _answered_within(item, 20))
    total = len(group)
    return {
        "interval": label,
        "incoming": total,
        "first_time": sum(1 for item in group if item.id in first_time),
        "operator_messages": op_msgs,
        "visitor_messages": cl_msgs,
        "avg_queue": _hms(queue),
        "avg_operator_queue": _hms(personal),
        "avg_missed_wait": _hms(missed_wait),
        "avg_reply": _hms(reply),
        "dialogs": len(active_dialogs),
        "answered_20s": answered_20,
        "pct_10s": _fmt_pct(sum(1 for item in group if _answered_within(item, 10)), total),
        "pct_20s": _fmt_pct(answered_20, total),
        "pct_30s": _fmt_pct(sum(1 for item in group if _answered_within(item, 30)), total),
        "pct_40s": _fmt_pct(sum(1 for item in group if _answered_within(item, 40)), total),
        "missed": len(missed),
        "rejected": sum(1 for item in group if _rejected(item)),
        "ignored_invites": sum(1 for item in group if _invitation_ignored(item)),
        "max_operators_online": _max_operators_online(start, end),
        "is_total": is_total,
    }


ONLINE_DATE_COLUMNS = [
    {"key": "interval", "label": "Дата"},
    {"key": "incoming", "label": "Обращений поступило"},
    {"key": "first_time", "label": "Запрос впервые"},
    {"key": "operator_messages", "label": "Сообщений операторов"},
    {"key": "visitor_messages", "label": "Сообщений посетителей"},
    {"key": "avg_queue", "label": "Среднее время, проведённое в очереди"},
    {"key": "avg_operator_queue", "label": "Среднее время ожидания оператора в его очереди"},
    {"key": "avg_missed_wait", "label": "Среднее время ожидания для пропущенных"},
    {"key": "avg_reply", "label": "Среднее время ответа на сообщение"},
    {"key": "dialogs", "label": "Диалогов"},
    {"key": "answered_20s", "label": "Ответ дан за 20 с."},
    {"key": "pct_10s", "label": "Ответ за 10 сек"},
    {"key": "pct_20s", "label": "Ответ за 20 сек"},
    {"key": "pct_30s", "label": "Ответ за 30 сек"},
    {"key": "pct_40s", "label": "Ответ за 40 сек"},
    {"key": "missed", "label": "Пропущенных"},
    {"key": "rejected", "label": "Отказов"},
    {"key": "ignored_invites", "label": "Непринятых приглашений"},
    {"key": "max_operators_online", "label": "Максимум операторов онлайн"},
]


def _offline_metric_row(
    *,
    label: str,
    group: list[Any],
    messages_map: dict[Any, list[Any]],
    start: datetime,
    end: datetime,
    with_max_ops: bool,
    is_total: bool = False,
) -> dict[str, Any]:
    assigned = [item for item in group if item.operator_id or item.accepted_at]
    processed = [item for item in group if _closed(item)]
    op_msgs = sum(_count_messages(messages_map.get(item.id, []), "operator") for item in group)
    queue = _avg(_queue_seconds(item) for item in group)
    personal = _avg(_personal_queue_seconds(item) for item in group)
    reply = _avg(first_response_seconds(item) for item in group)
    row = {
        "interval": label,
        "queued": len(group),
        "assigned": len(assigned),
        "processed": len(processed),
        "operator_messages": op_msgs,
        "avg_queue": _hms(queue),
        "avg_operator_queue": _hms(personal),
        "avg_reply": _hms(reply),
        "is_total": is_total,
    }
    if with_max_ops:
        row["max_operators_online"] = _max_operators_online(start, end)
    return row


OFFLINE_DATE_COLUMNS = [
    {"key": "interval", "label": "Дата"},
    {"key": "queued", "label": "Офлайновых попало в общую очередь"},
    {"key": "assigned", "label": "Офлайновых назначено на оператора"},
    {"key": "processed", "label": "Обработанных офлайн"},
    {"key": "operator_messages", "label": "Сообщений операторов"},
    {
        "key": "avg_queue",
        "label": "Сколько времени в среднем проводит офлайн-обращение в очереди до того момента, когда его начнёт обрабатывать оператор.",
    },
    {"key": "avg_operator_queue", "label": "Среднее время ожидания оператора в его очереди"},
    {
        "key": "avg_reply",
        "label": "Среднее время получения ответа на сообщение посетителя для офлайн",
    },
    {"key": "max_operators_online", "label": "Максимум операторов онлайн"},
]


def report_chat_categories(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    from online_chat.models import DialogCloseTopicNode

    dialogs = list(
        dialogs_in_period(date_from, date_to, **filters).select_related("close_topic_node")
    )
    closed = [item for item in dialogs if _closed(item)]
    counts: dict[str, int] = defaultdict(int)
    for dialog in closed:
        counts[_category_name(dialog)] += 1
    labels = [
        node.label
        for node in DialogCloseTopicNode.objects.filter(parent__isnull=True).order_by(
            "sort_order", "label"
        )
    ]
    for name in counts:
        if name not in labels:
            labels.append(name)
    if "Без категории" not in labels:
        labels.append("Без категории")
    total = len(closed)
    rows = []
    for name in labels:
        closed_count = counts.get(name, 0)
        rows.append(
            {
                "category": name,
                "closed": closed_count,
                "share_pct": _fmt_pct(closed_count, total),
            }
        )
    rows.append({"category": "Итого", "closed": total, "share_pct": 100.0 if total else 0.0, "is_total": True})
    chart = [
        {"label": row["category"][:24], "value": row["closed"]}
        for row in rows
        if not row.get("is_total") and row["closed"]
    ]
    return _payload(
        title="Статистика по категориям",
        columns=[
            {"key": "category", "label": "Категория"},
            {"key": "closed", "label": "Обращений закрыто"},
            {"key": "share_pct", "label": "% от обращений"},
        ],
        rows=rows,
        chart=chart,
        summary={"closed": total, "categories": max(0, len(rows) - 1)},
    )


def _department_rows(dialogs: list[Any]) -> list[dict[str, Any]]:
    from online_chat.models import Department

    names = list(Department.objects.filter(is_active=True).order_by("priority", "name").values_list("name", flat=True))
    incoming: dict[str, int] = defaultdict(int)
    closed: dict[str, int] = defaultdict(int)
    for dialog in dialogs:
        name = _dept_name(dialog)
        incoming[name] += 1
        if _closed(dialog):
            closed[name] += 1
        if name not in names:
            names.append(name)
    if "Без отдела" not in names:
        names.append("Без отдела")
    rows = [
        {
            "department": name,
            "incoming": incoming.get(name, 0),
            "closed": closed.get(name, 0),
        }
        for name in names
    ]
    rows.append(
        {
            "department": "Итого",
            "incoming": len(dialogs),
            "closed": sum(1 for item in dialogs if _closed(item)),
            "is_total": True,
        }
    )
    return rows


def report_chat_dept_online(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs, _ = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    rows = _department_rows(dialogs)
    return _payload(
        title="По отделам (онлайн)",
        columns=[
            {"key": "department", "label": "Отдел"},
            {"key": "incoming", "label": "Обращений поступило"},
            {"key": "closed", "label": "Обращений закрыто"},
        ],
        rows=rows,
        chart=[{"label": row["department"][:24], "value": row["incoming"]} for row in rows if not row.get("is_total")],
        summary={"incoming": rows[-1]["incoming"] if rows else 0, "closed": rows[-1]["closed"] if rows else 0},
    )


def report_chat_dept_offline(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    _, dialogs = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    rows = _department_rows(dialogs)
    return _payload(
        title="По отделам (офлайн)",
        columns=[
            {"key": "department", "label": "Отдел"},
            {"key": "incoming", "label": "Обращений поступило"},
            {"key": "closed", "label": "Обращений закрыто"},
        ],
        rows=rows,
        chart=[{"label": row["department"][:24], "value": row["incoming"]} for row in rows if not row.get("is_total")],
        summary={"incoming": rows[-1]["incoming"] if rows else 0, "closed": rows[-1]["closed"] if rows else 0},
    )


def report_chat_dates_online(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs, _ = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    messages_map = _load_messages(dialogs)
    first_time = _first_time_ids(dialogs, date_from)
    period_start, period_end = _period_bounds(date_from, date_to)
    by_day: dict[date, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        by_day[dialog.created_at.date()].append(dialog)
    rows = []
    day = date_from
    while day <= date_to:
        start, end = _day_bounds(day)
        rows.append(
            _online_metric_row(
                label=_date_label(day),
                group=by_day.get(day, []),
                messages_map=messages_map,
                first_time=first_time,
                start=start,
                end=end,
            )
        )
        day += timedelta(days=1)
    rows.append(
        _online_metric_row(
            label="Итого",
            group=dialogs,
            messages_map=messages_map,
            first_time=first_time,
            start=period_start,
            end=period_end,
            is_total=True,
        )
    )
    columns = list(ONLINE_DATE_COLUMNS)
    return _payload(
        title="Статистика использования системы по датам",
        columns=columns,
        rows=rows,
        chart=[{"label": row["interval"], "value": row["incoming"]} for row in rows if not row.get("is_total")],
        summary={"incoming": rows[-1]["incoming"] if rows else 0},
    )


def report_chat_dates_offline(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    _, dialogs = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    messages_map = _load_messages(dialogs)
    period_start, period_end = _period_bounds(date_from, date_to)
    by_day: dict[date, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        by_day[dialog.created_at.date()].append(dialog)
    rows = []
    day = date_from
    while day <= date_to:
        start, end = _day_bounds(day)
        rows.append(
            _offline_metric_row(
                label=_date_label(day),
                group=by_day.get(day, []),
                messages_map=messages_map,
                start=start,
                end=end,
                with_max_ops=True,
            )
        )
        day += timedelta(days=1)
    rows.append(
        _offline_metric_row(
            label="Итого",
            group=dialogs,
            messages_map=messages_map,
            start=period_start,
            end=period_end,
            with_max_ops=True,
            is_total=True,
        )
    )
    return _payload(
        title="Статистика использования системы по датам для офлайн-обращений",
        columns=OFFLINE_DATE_COLUMNS,
        rows=rows,
        chart=[{"label": row["interval"], "value": row["queued"]} for row in rows if not row.get("is_total")],
        summary={"queued": rows[-1]["queued"] if rows else 0},
    )


def _group_by_hour(dialogs: list[Any]) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        grouped[dialog.created_at.hour].append(dialog)
    return grouped


def report_chat_hours_online(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs, _ = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    messages_map = _load_messages(dialogs)
    first_time = _first_time_ids(dialogs, date_from)
    period_start, period_end = _period_bounds(date_from, date_to)
    by_hour = _group_by_hour(dialogs)
    hours = sorted(by_hour) or list(range(9, 21))
    rows = []
    for hour in hours:
        start = period_start.replace(hour=hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        row = _online_metric_row(
            label=_hour_label(hour),
            group=by_hour.get(hour, []),
            messages_map=messages_map,
            first_time=first_time,
            start=start,
            end=end,
        )
        rows.append(row)
    rows.append(
        _online_metric_row(
            label="Итого",
            group=dialogs,
            messages_map=messages_map,
            first_time=first_time,
            start=period_start,
            end=period_end,
            is_total=True,
        )
    )
    columns = [{"key": "interval", "label": "Временной интервал"}] + ONLINE_DATE_COLUMNS[1:]
    return _payload(
        title="Статистика использования системы по часам",
        columns=columns,
        rows=rows,
        chart=[{"label": row["interval"], "value": row["incoming"]} for row in rows if not row.get("is_total")],
        summary={"incoming": rows[-1]["incoming"] if rows else 0},
    )


def report_chat_hours_offline(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    _, dialogs = _split_online_offline(list(dialogs_in_period(date_from, date_to, **filters)))
    messages_map = _load_messages(dialogs)
    period_start, period_end = _period_bounds(date_from, date_to)
    by_hour = _group_by_hour(dialogs)
    hours = sorted(by_hour) or list(range(8, 24))
    rows = []
    for hour in hours:
        start = period_start.replace(hour=hour, minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        rows.append(
            _offline_metric_row(
                label=_hour_label(hour),
                group=by_hour.get(hour, []),
                messages_map=messages_map,
                start=start,
                end=end,
                with_max_ops=False,
            )
        )
    rows.append(
        _offline_metric_row(
            label="Итого",
            group=dialogs,
            messages_map=messages_map,
            start=period_start,
            end=period_end,
            with_max_ops=False,
            is_total=True,
        )
    )
    columns = [
        {"key": "interval", "label": "Временной интервал"},
        *OFFLINE_DATE_COLUMNS[1:-1],
    ]
    return _payload(
        title="Статистика использования системы по часам для офлайн-обращений",
        columns=columns,
        rows=rows,
        chart=[{"label": row["interval"], "value": row["queued"]} for row in rows if not row.get("is_total")],
        summary={"queued": rows[-1]["queued"] if rows else 0},
    )


OPERATOR_COLUMNS = [
    {"key": "operator", "label": "Оператор"},
    {"key": "dialogs", "label": "Обработано диалогов"},
    {"key": "answered_20s", "label": "Ответ дан за 20 с."},
    {"key": "offline_assigned", "label": "Офлайновых назначено на оператора"},
    {"key": "offline_processed", "label": "Обработанных офлайн"},
    {"key": "messages", "label": "Сообщений оператора (онлайн плюс офлайн)"},
    {"key": "avg_length", "label": "Средняя длина сообщения (в символах)"},
    {"key": "rating", "label": "Средний рейтинг оператора"},
    {"key": "avg_queue", "label": "Среднее время ожидания оператора в его очереди"},
    {"key": "invited", "label": "Кол-во приглашённых посетителей"},
    {"key": "ignored_invites", "label": "Непринятых приглашений"},
    {"key": "transfers_out", "label": "Кол-во переводов из отдела"},
    {"key": "transfers_in", "label": "Кол-во переводов в отдел"},
    {"key": "busy_notices", "label": "Кол-во сообщений о занятости оператора"},
]


def _operator_stats(
    dialogs: list[Any],
    messages_map: dict[Any, list[Any]],
    events_map: dict[Any, list[Any]],
    *,
    include_empty: bool = False,
) -> list[dict[str, Any]]:
    from online_chat.models import OperatorProfile

    by_name: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        name = (dialog.operator_name or "").strip()
        if name:
            by_name[name].append(dialog)
    names = sorted(by_name)
    if include_empty:
        extra = list(
            OperatorProfile.objects.filter(is_active=True)
            .order_by("display_name")
            .values_list("display_name", flat=True)
        )
        for name in extra:
            if name not in by_name:
                names.append(name)
    rows = []
    for name in names:
        group = by_name.get(name, [])
        online, offline = _split_online_offline(group)
        processed = [item for item in online if item.accepted_at or item.first_response_at]
        messages = []
        chars = 0
        for dialog in group:
            for message in messages_map.get(dialog.id, []):
                if message.speaker == "operator" and not message.is_deleted:
                    messages.append(message)
                    chars += len(message.text or "")
        ratings = []
        for dialog in group:
            try:
                feedback = dialog.feedback
            except Exception:  # noqa: BLE001
                feedback = None
            if feedback is not None:
                ratings.append(int(feedback.rating))
        transfers_out = 0
        transfers_in = 0
        busy = 0
        for dialog in group:
            for event in events_map.get(dialog.id, []):
                if event.type == "transferred":
                    if (event.payload or {}).get("from") == name:
                        transfers_out += 1
                    if (event.payload or {}).get("to") == name:
                        transfers_in += 1
                if event.type in {"operator_busy", "busy_notice"}:
                    busy += 1
        invited = [
            item
            for item in group
            if getattr(item, "initiated_by", "") == "operator" and item.first_response_at
        ]
        ignored = [item for item in group if _invitation_ignored(item)]
        rows.append(
            {
                "operator": name,
                "dialogs": len(processed),
                "answered_20s": sum(1 for item in group if _answered_within(item, 20)),
                "offline_assigned": sum(1 for item in offline if item.accepted_at or item.operator_id),
                "offline_processed": sum(1 for item in offline if _closed(item)),
                "messages": len(messages),
                "avg_length": round(chars / len(messages), 2) if messages else 0,
                "rating": _rating_text(ratings),
                "avg_queue": _hms(_avg(_personal_queue_seconds(item) for item in group)),
                "invited": len(invited),
                "ignored_invites": len(ignored),
                "transfers_out": transfers_out,
                "transfers_in": transfers_in,
                "busy_notices": busy,
            }
        )
    return rows


def report_chat_operators_daily(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    if (date_to - date_from).days > 6:
        return _payload(
            title="Статистика по операторам",
            columns=[{"key": "operator", "label": "Оператор"}],
            rows=[
                {
                    "operator": (
                        "Отчёт строится только для периода не длиннее 7 дней. "
                        "Используйте «Суммарная статистика по операторам»."
                    )
                }
            ],
            summary={"limited": True},
        )
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    messages_map = _load_messages(dialogs)
    events_map = _events_by_dialog(dialogs)
    by_day: dict[date, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        by_day[dialog.created_at.date()].append(dialog)
    rows: list[dict[str, Any]] = []
    day = date_from
    while day <= date_to:
        rows.append({"operator": _date_label(day), "is_section": True})
        rows.extend(_operator_stats(by_day.get(day, []), messages_map, events_map))
        day += timedelta(days=1)
    chart = [
        {"label": row["operator"][:18], "value": row.get("dialogs") or 0}
        for row in rows
        if not row.get("is_section")
    ]
    return _payload(
        title="Статистика по операторам",
        columns=OPERATOR_COLUMNS,
        rows=rows,
        chart=chart[:12],
        summary={"operators": sum(1 for row in rows if not row.get("is_section"))},
    )


def report_chat_operators_summary(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    messages_map = _load_messages(dialogs)
    events_map = _events_by_dialog(dialogs)
    rows = _operator_stats(dialogs, messages_map, events_map)
    totals = {
        "operator": "Итого",
        "dialogs": sum(row["dialogs"] for row in rows),
        "answered_20s": sum(row["answered_20s"] for row in rows),
        "offline_assigned": sum(row["offline_assigned"] for row in rows),
        "offline_processed": sum(row["offline_processed"] for row in rows),
        "messages": sum(row["messages"] for row in rows),
        "avg_length": (
            round(
                sum(row["avg_length"] * row["messages"] for row in rows) / sum(row["messages"] for row in rows),
                2,
            )
            if sum(row["messages"] for row in rows)
            else 0
        ),
        "rating": "—",
        "avg_queue": "—",
        "invited": sum(row["invited"] for row in rows),
        "ignored_invites": sum(row["ignored_invites"] for row in rows),
        "transfers_out": sum(row["transfers_out"] for row in rows),
        "transfers_in": sum(row["transfers_in"] for row in rows),
        "busy_notices": sum(row["busy_notices"] for row in rows),
        "is_total": True,
    }
    ratings: list[int] = []
    for dialog in dialogs:
        try:
            feedback = dialog.feedback
        except Exception:  # noqa: BLE001
            feedback = None
        if feedback is not None:
            ratings.append(int(feedback.rating))
    totals["rating"] = _rating_text(ratings)
    totals["avg_queue"] = _hms(_avg(_personal_queue_seconds(item) for item in dialogs))
    rows.append(totals)
    return _payload(
        title="Суммарная статистика по операторам",
        columns=OPERATOR_COLUMNS,
        rows=rows,
        chart=[
            {"label": row["operator"][:18], "value": row["dialogs"]}
            for row in rows
            if not row.get("is_total")
        ],
        summary={"operators": max(0, len(rows) - 1), "dialogs": totals["dialogs"]},
    )


def report_chat_missed(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = [item for item in dialogs_in_period(date_from, date_to, **filters) if _missed(item)]
    by_name: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        name = (dialog.operator_name or "").strip() or "Без оператора"
        by_name[name].append(dialog)
    rows = []
    for name, group in sorted(by_name.items()):
        rows.append(
            {
                "operator": name,
                "missed": len(group),
                "avg_wait": _hms(_avg(_queue_seconds(item) for item in group)),
            }
        )
    if rows:
        rows.append(
            {
                "operator": "Итого",
                "missed": len(dialogs),
                "avg_wait": _hms(_avg(_queue_seconds(item) for item in dialogs)),
                "is_total": True,
            }
        )
    return _payload(
        title="Статистика по пропущенным посетителям",
        columns=[
            {"key": "operator", "label": "Оператор"},
            {"key": "missed", "label": "Кол-во пропущенных посетителей"},
            {"key": "avg_wait", "label": "Среднее время ожидания для пропущенных"},
        ],
        rows=rows,
        chart=[{"label": row["operator"][:18], "value": row["missed"]} for row in rows if not row.get("is_total")],
        summary={"missed": len(dialogs)},
    )


def _overlap_seconds(start: datetime, end: datetime, window_start: datetime, window_end: datetime) -> float:
    left = max(start, window_start)
    right = min(end, window_end)
    return max(0.0, (right - left).total_seconds())


def _union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    if not intervals:
        return 0.0
    ordered = sorted(intervals, key=lambda item: item[0])
    current_start, current_end = ordered[0]
    total = 0.0
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += (current_end - current_start).total_seconds()
            current_start, current_end = start, end
    total += (current_end - current_start).total_seconds()
    return max(0.0, total)


def _concurrency_buckets(intervals: list[tuple[datetime, datetime]]) -> tuple[float, float, float]:
    events: list[tuple[datetime, int]] = []
    for start, end in intervals:
        if end <= start:
            continue
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))
    one = two = three = 0.0
    active = 0
    prev: datetime | None = None
    for moment, delta in events:
        if prev is not None and moment > prev:
            duration = (moment - prev).total_seconds()
            if active == 1:
                one += duration
            elif active == 2:
                two += duration
            elif active >= 3:
                three += duration
        active += delta
        prev = moment
    return one, two, three


def report_chat_time_usage(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    from django.db.utils import OperationalError, ProgrammingError
    from online_chat.models import OperatorPresenceLog, OperatorProfile

    window_start, window_end = _period_bounds(date_from, date_to)
    messenger = filters.get("messenger") or ""
    department_id = filters.get("department_id") or ""
    dialogs = list(dialogs_in_period(date_from, date_to, messenger=messenger, department_id=department_id))
    operators = list(OperatorProfile.objects.filter(is_active=True).order_by("display_name"))
    try:
        logs = list(
            OperatorPresenceLog.objects.filter(
                operator_id__in=[item.id for item in operators],
                started_at__lt=window_end,
            ).filter(Q(ended_at__isnull=True) | Q(ended_at__gt=window_start))
        )
    except (OperationalError, ProgrammingError):
        logs = []
    logs_by_op: dict[Any, list[Any]] = defaultdict(list)
    for log in logs:
        logs_by_op[log.operator_id].append(log)

    presence_keys = {
        "online": "time_online",
        "lunch": "lunch",
        "training": "training",
        "tech_issue": "tech",
        "meeting": "meeting",
        "break": "short_break",
        "offline": "invisible",
        "busy": "phone",
    }
    rows = []
    for operator in operators:
        presence_seconds = {key: 0.0 for key in presence_keys.values()}
        for log in logs_by_op.get(operator.id, []):
            end = log.ended_at or window_end
            seconds = _overlap_seconds(log.started_at, end, window_start, window_end)
            field = presence_keys.get(log.presence)
            if field:
                presence_seconds[field] += seconds
        mine = [
            item
            for item in dialogs
            if item.operator_id == operator.id or item.operator_name == operator.display_name
        ]
        intervals: list[tuple[datetime, datetime]] = []
        offline_process = 0.0
        for dialog in mine:
            start = dialog.accepted_at or dialog.created_at
            end = dialog.closed_at or window_end
            if start is None:
                continue
            overlap = _overlap_seconds(start, end, window_start, window_end)
            if overlap <= 0:
                continue
            intervals.append((max(start, window_start), min(end, window_end)))
            if _is_offline(dialog):
                offline_process += overlap
        one, two, three = _concurrency_buckets(intervals)
        in_dialogs = _union_seconds(intervals)
        summed = one + two + three
        rows.append(
            {
                "operator": operator.display_name,
                "time_online": _hms(presence_seconds["time_online"]),
                "time_in_dialogs": _hms(in_dialogs),
                "time_in_dialogs_sum": _hms(summed),
                "one_chat": _hms(one),
                "two_chats": _hms(two),
                "three_chats": _hms(three),
                "avg_dialog": _hms(summed / len(intervals) if intervals else 0),
                "phone": _hms(presence_seconds["phone"]),
                "lunch": _hms(presence_seconds["lunch"]),
                "training": _hms(presence_seconds["training"]),
                "tech": _hms(presence_seconds["tech"]),
                "meeting": _hms(presence_seconds["meeting"]),
                "short_break": _hms(presence_seconds["short_break"]),
                "invisible": _hms(presence_seconds["invisible"]),
                "offline_process": _hms(offline_process),
            }
        )

    def _sum_hms(key: str) -> str:
        total = 0
        for row in rows:
            parts = str(row[key]).split(":")
            if len(parts) != 3:
                continue
            total += int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return _hms(total)

    if rows:
        rows.append(
            {
                "operator": "Итого",
                "time_online": _sum_hms("time_online"),
                "time_in_dialogs": _sum_hms("time_in_dialogs"),
                "time_in_dialogs_sum": _sum_hms("time_in_dialogs_sum"),
                "one_chat": _sum_hms("one_chat"),
                "two_chats": _sum_hms("two_chats"),
                "three_chats": _sum_hms("three_chats"),
                "avg_dialog": "—",
                "phone": _sum_hms("phone"),
                "lunch": _sum_hms("lunch"),
                "training": _sum_hms("training"),
                "tech": _sum_hms("tech"),
                "meeting": _sum_hms("meeting"),
                "short_break": _sum_hms("short_break"),
                "invisible": _sum_hms("invisible"),
                "offline_process": _sum_hms("offline_process"),
                "is_total": True,
            }
        )
    return _payload(
        title="Статистика по использованию времени операторами",
        columns=[
            {"key": "operator", "label": "Оператор"},
            {"key": "time_online", "label": "Время онлайн"},
            {"key": "time_in_dialogs", "label": "Время в диалогах"},
            {"key": "time_in_dialogs_sum", "label": "Суммарное время в диалогах"},
            {"key": "one_chat", "label": "Время с одним диалогом"},
            {"key": "two_chats", "label": "Время с двумя диалогами"},
            {"key": "three_chats", "label": "Время c тремя и более диалогами"},
            {"key": "avg_dialog", "label": "Среднее время в диалоге"},
            {"key": "phone", "label": "На телефоне"},
            {"key": "lunch", "label": "Обед"},
            {"key": "training", "label": "На проведении инструктажа"},
            {"key": "tech", "label": "Технический перерыв"},
            {"key": "meeting", "label": "На встрече"},
            {"key": "short_break", "label": "Короткий перерыв"},
            {"key": "invisible", "label": "Невидимка"},
            {"key": "offline_process", "label": "Обработка офлайн-обращений"},
        ],
        rows=rows,
        chart=[
            {"label": row["operator"][:18], "value": 1}
            for row in rows
            if not row.get("is_total")
        ],
        summary={"operators": max(0, len(rows) - (1 if rows else 0))},
    )
