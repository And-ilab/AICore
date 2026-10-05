"""Production aggregations for online-chat → II.6 reports (telephony out of scope)."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import mean
from typing import Any, Iterable

from django.db.models import Avg, Count, Q, QuerySet
from django.utils import timezone as dj_tz

SLA_FIRST_RESPONSE_SECONDS = 120  # fallback if DB settings unavailable
CHAT_MESSENGERS = frozenset({"widget", "telegram", "viber", "vk", "ok", "api", "email"})

CHANNEL_LABELS = {
    "widget": "Виджет сайта",
    "telegram": "Telegram",
    "viber": "Viber",
    "vk": "ВКонтакте",
    "ok": "Одноклассники",
    "api": "API",
    "email": "E-mail",
    "chat": "Онлайн-чат",
    "online_chat": "Онлайн-чат",
    "telephony": "Телефония",
    "phone": "Телефония",
}

OUTCOME_LABELS = {
    "resolved": "Решён",
    "rejected": "Отказ клиента",
    "lost": "Потерянный",
    "offline": "Офлайн",
    "escalated": "Эскалация",
    "": "Не определён",
}

STATUS_LABELS = {
    "waiting": "В очереди",
    "active": "В работе",
    "closed": "Закрыт",
    "blocked": "Заблокирован",
}

FEEDBACK_LABELS = {
    "used": "Воспользовался",
    "partial": "Неполный ответ",
    "not_used": "Не воспользовался",
}

SOURCE_LABELS = {
    "chat": "Онлайн-чат",
    "telephony": "Телефония",
}


def _feedback_source(fb: Any) -> str:
    source = ""
    if hasattr(fb, "source"):
        source = str(getattr(fb, "source", "") or "").strip().lower()
    if source in {"telephony", "phone", "call"}:
        return "telephony"
    if source in {"chat", "online_chat", "widget"}:
        return "chat"
    dialog = getattr(fb, "dialog", None)
    channel = str(getattr(dialog, "channel", None) or "").strip().lower() if dialog else ""
    if channel in {"telephony", "phone"}:
        return "telephony"
    return "chat"


TELEPHONY_SOURCES = ("telephony", "phone", "call")

RELEVANCE_BUCKET_LABELS = (
    ("high", "Высокая (≥80%)"),
    ("mid", "Средняя (50–79%)"),
    ("low", "Низкая (<50%)"),
)


def _classify_relevance(percent: Any) -> str | None:
    if percent is None:
        return None
    try:
        value = float(percent)
    except (TypeError, ValueError):
        return None
    if value >= 80:
        return "high"
    if value >= 50:
        return "mid"
    return "low"


def _relevance_bucket_chart(counts: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"label": label, "value": counts.get(key, 0)}
        for key, label in RELEVANCE_BUCKET_LABELS
        if counts.get(key, 0)
    ]


def _sufler_source_filter(filters: dict[str, Any] | None) -> str:
    """Map catalog channel to hint source. Only for sufler stats screen."""
    if not filters:
        return ""
    if str(filters.get("scope") or "").strip().lower() != "sufler":
        return ""
    channel = str(filters.get("channel") or "").strip().lower()
    if channel in {"telephony", "phone"}:
        return "telephony"
    if channel in {"online_chat", "chat"}:
        return "chat"
    return ""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def channel_label(channel: str) -> str:
    key = (channel or "").strip().lower()
    return CHANNEL_LABELS.get(key, channel or "неизвестный")


def dialog_rating(dialog: Any) -> int | None:
    try:
        feedback = dialog.feedback
    except Exception:  # noqa: BLE001 — OneToOne may be missing
        return None
    if feedback is None:
        return None
    return int(feedback.rating)


def dialogs_in_period(
    date_from: date,
    date_to: date,
    *,
    messenger: str = "",
    department_id: str = "",
    topic: str = "",
    status: str = "",
    outcome: str = "",
) -> QuerySet[Any]:
    from online_chat.models import Dialog

    qs = Dialog.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    if messenger and messenger not in {"all", "online_chat", ""}:
        qs = qs.filter(channel=messenger)
    if department_id and department_id not in {"all", ""}:
        qs = qs.filter(department_id=department_id)
    if topic and topic not in {"all", ""}:
        qs = qs.filter(close_topic=topic)
    if status and status not in {"all", ""}:
        if status in {"offline", "lost", "rejected", "declined"}:
            mapped = "rejected" if status == "declined" else status
            qs = qs.filter(Q(outcome=mapped) | Q(status=status))
        else:
            qs = qs.filter(status=status)
    if outcome and outcome not in {"all", ""}:
        qs = qs.filter(outcome=outcome)
    return qs.select_related("department", "operator", "feedback")


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 1)
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 1)


def _avg(values: Iterable[float | None]) -> float | None:
    cleaned = [float(v) for v in values if v is not None]
    if not cleaned:
        return None
    return round(mean(cleaned), 2)


def first_response_seconds(dialog: Any) -> float | None:
    return _seconds_between(dialog.created_at, dialog.first_response_at)


def wait_seconds(dialog: Any, *, now: datetime | None = None) -> float | None:
    if dialog.accepted_at:
        return _seconds_between(dialog.created_at, dialog.accepted_at)
    if dialog.status == "waiting":
        return _seconds_between(dialog.created_at, now or _utcnow())
    return None


def aht_seconds(dialog: Any) -> float | None:
    start = dialog.accepted_at or dialog.created_at
    return _seconds_between(start, dialog.closed_at)


def get_sla_first_response_seconds() -> int:
    """Target seconds for first operator reply (admin-configurable)."""
    try:
        from online_chat.models import ServiceLevelSettings

        value = int(ServiceLevelSettings.get_solo().first_response_seconds)
        return value if value > 0 else SLA_FIRST_RESPONSE_SECONDS
    except Exception:  # noqa: BLE001 — reports must not fail if chat app unavailable
        return SLA_FIRST_RESPONSE_SECONDS


def within_sla(dialog: Any, *, target: int | None = None) -> bool | None:
    frt = first_response_seconds(dialog)
    if frt is None:
        return None
    limit = get_sla_first_response_seconds() if target is None else target
    return frt <= limit


def _sufler_demo_stats(date_to: date, *, source: str = "") -> dict[str, Any]:
    """Stand-in rows so Hub «Статистика суфлёра» is not empty before live feedback."""
    at = f"{date_to.isoformat()}T14:28:00+03:00"
    chat = {
        "channel": "chat",
        "label": SOURCE_LABELS["chat"],
        "useful_pct": 72.0,
        "incomplete_pct": 18.0,
        "unused_pct": 10.0,
        "sessions": 148,
        "avg_relevance": 88.0,
        "used": 106,
        "partial": 27,
        "not_used": 15,
    }
    phone = {
        "channel": "telephony",
        "label": SOURCE_LABELS["telephony"],
        "useful_pct": 61.0,
        "incomplete_pct": 22.0,
        "unused_pct": 17.0,
        "sessions": 100,
        "avg_relevance": 81.0,
        "used": 61,
        "partial": 22,
        "not_used": 17,
    }
    sources = [phone] if source == "telephony" else [chat] if source == "chat" else [chat, phone]
    used = sum(item["used"] for item in sources)
    partial = sum(item["partial"] for item in sources)
    unused = sum(item["not_used"] for item in sources)
    total = used + partial + unused
    examples = [
        {
            "reason": "Оператор не воспользовался подсказкой",
            "count": 1,
            "example": "Лимит снятия наличных в банкомате",
            "channel": "chat",
            "operator": "Васильева Е.К.",
            "relevance_pct": 69,
            "at": at,
        },
        {
            "reason": "Оператор не воспользовался подсказкой",
            "count": 1,
            "example": "Комиссия за перевод в РФ",
            "channel": "telephony",
            "operator": "Орлов Н.В.",
            "relevance_pct": 54,
            "at": at,
        },
        {
            "reason": "Оператор не воспользовался подсказкой",
            "count": 1,
            "example": "Блокировка карты при утрате",
            "channel": "chat",
            "operator": "Иванов И.И.",
            "relevance_pct": 61,
            "at": at,
        },
        {
            "reason": "Оператор не воспользовался подсказкой",
            "count": 1,
            "example": "Смена ПИН-кода в банкомате",
            "channel": "telephony",
            "operator": "Сидорова А.П.",
            "relevance_pct": 58,
            "at": at,
        },
    ]
    if source == "telephony":
        examples = [row for row in examples if row["channel"] == "telephony"]
    elif source == "chat":
        examples = [row for row in examples if row["channel"] == "chat"]
    topics = [
        {
            "channel": "chat",
            "channel_label": SOURCE_LABELS["chat"],
            "topic": "Карты и счета",
            "avg_relevance": 91.0,
            "answers": 64,
            "used_pct": 78.0,
        },
        {
            "channel": "telephony",
            "channel_label": SOURCE_LABELS["telephony"],
            "topic": "Кредиты",
            "avg_relevance": 74.0,
            "answers": 41,
            "used_pct": 61.0,
        },
        {
            "channel": "chat",
            "channel_label": SOURCE_LABELS["chat"],
            "topic": "ЕРИП",
            "avg_relevance": 88.0,
            "answers": 29,
            "used_pct": 76.0,
        },
        {
            "channel": "telephony",
            "channel_label": SOURCE_LABELS["telephony"],
            "topic": "Лимиты ATM",
            "avg_relevance": 69.0,
            "answers": 22,
            "used_pct": 45.0,
        },
    ]
    if source == "telephony":
        topics = [row for row in topics if row["channel"] == "telephony"]
    elif source == "chat":
        topics = [row for row in topics if row["channel"] == "chat"]
    return {
        "total": total,
        "used_pct": round(100 * used / total, 1),
        "partial_pct": round(100 * partial / total, 1),
        "unused_pct": round(100 * unused / total, 1),
        "avg_relevance": round(
            sum(item["avg_relevance"] * item["sessions"] for item in sources) / total,
            1,
        ),
        "by_choice": [
            {
                "label": FEEDBACK_LABELS[choice],
                "choice": choice,
                "value": count,
                "pct": round(100 * count / total, 1),
            }
            for choice, count in (
                ("used", used),
                ("partial", partial),
                ("not_used", unused),
            )
        ],
        "by_channel_topic": topics,
        "by_source": sources,
        "recent": [],
        "examples_not_used": examples,
        "relevance_buckets": {
            "high": round(total * 0.58),
            "mid": round(total * 0.30),
            "low": max(0, total - round(total * 0.58) - round(total * 0.30)),
        },
        "demo": True,
    }


def sufler_stats(
    date_from: date,
    date_to: date,
    *,
    source: str = "",
) -> dict[str, Any]:
    from online_chat.models import SuflerHintFeedback

    qs = SuflerHintFeedback.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    )
    source = (source or "").strip().lower()
    if source in {"online_chat", "widget"}:
        source = "chat"
    if source == "phone":
        source = "telephony"
    if source == "telephony":
        qs = qs.filter(source__in=TELEPHONY_SOURCES)
    elif source == "chat":
        qs = qs.exclude(source__in=TELEPHONY_SOURCES)
    total = qs.count()
    if not total:
        return _sufler_demo_stats(date_to, source=source)

    by_choice = {
        row["choice"]: row["c"]
        for row in qs.values("choice").annotate(c=Count("id"))
    }
    used = by_choice.get("used", 0)
    partial = by_choice.get("partial", 0)
    unused = by_choice.get("not_used", 0)
    avg_rel = qs.exclude(relevance_percent=None).aggregate(v=Avg("relevance_percent"))["v"]

    topic_rows: list[tuple[str, str, Any, Any]] = []
    by_source_acc: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"used": 0, "partial": 0, "not_used": 0, "rels": [], "total": 0}
    )
    buckets = {"high": 0, "mid": 0, "low": 0}
    for fb in qs.select_related("dialog")[:2000]:
        channel = _feedback_source(fb)
        topic = (getattr(fb.dialog, "close_topic", None) or "").strip() or "Без тематики"
        topic_rows.append((channel, topic, fb.relevance_percent, fb.choice))
        acc = by_source_acc[channel]
        acc["total"] += 1
        acc[fb.choice] = acc.get(fb.choice, 0) + 1
        if fb.relevance_percent is not None:
            acc["rels"].append(fb.relevance_percent)
        bucket = _classify_relevance(fb.relevance_percent)
        if bucket:
            buckets[bucket] += 1

    grouped: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for channel, topic, rel, choice in topic_rows:
        grouped[(channel, topic)].append((rel, choice))

    by_channel_topic = []
    for (channel, topic), items in sorted(grouped.items(), key=lambda x: -len(x[1]))[:30]:
        rels = [r for r, _ in items if r is not None]
        by_channel_topic.append(
            {
                "channel": channel,
                "channel_label": channel_label(channel),
                "topic": topic,
                "avg_relevance": round(mean(rels), 1) if rels else None,
                "answers": len(items),
                "used_pct": round(
                    100 * sum(1 for _, c in items if c == "used") / len(items), 1
                ),
            }
        )

    by_source = []
    for key in ("chat", "telephony"):
        acc = by_source_acc.get(key)
        if not acc:
            continue
        total_source = acc["total"] or 1
        rels = acc["rels"]
        by_source.append(
            {
                "channel": key,
                "label": SOURCE_LABELS[key],
                "useful_pct": round(100 * acc["used"] / total_source, 1),
                "incomplete_pct": round(100 * acc["partial"] / total_source, 1),
                "unused_pct": round(100 * acc["not_used"] / total_source, 1),
                "sessions": acc["total"],
                "avg_relevance": round(mean(rels), 1) if rels else None,
                "used": acc["used"],
                "partial": acc["partial"],
                "not_used": acc["not_used"],
            }
        )

    recent = []
    for fb in qs.select_related("dialog").order_by("-created_at")[:40]:
        dialog = fb.dialog
        recent.append(
            {
                "id": str(fb.id),
                "channel": _feedback_source(fb),
                "operator": fb.operator_name or "—",
                "topic": (getattr(dialog, "close_topic", None) or "").strip() or "—",
                "relevance_pct": fb.relevance_percent,
                "feedback": fb.choice,
                "query": (fb.query or "")[:160],
                "hint": (fb.hint_text or "")[:200],
                "at": fb.created_at.isoformat(),
                "dialog_id": str(dialog.id) if dialog else "",
                "ref": dialog.ref_code() if dialog else "—",
            }
        )

    examples = []
    for fb in qs.filter(choice="not_used").select_related("dialog").order_by("-created_at")[:25]:
        examples.append(
            {
                "reason": "Оператор не воспользовался подсказкой",
                "count": 1,
                "example": (fb.query or fb.hint_text or "—")[:180],
                "channel": _feedback_source(fb),
                "operator": fb.operator_name or "—",
                "relevance_pct": fb.relevance_percent,
                "at": fb.created_at.isoformat(),
            }
        )

    return {
        "total": total,
        "used_pct": round(100 * used / total, 1),
        "partial_pct": round(100 * partial / total, 1),
        "unused_pct": round(100 * unused / total, 1),
        "avg_relevance": round(float(avg_rel), 1) if avg_rel is not None else None,
        "by_choice": [
            {
                "label": FEEDBACK_LABELS.get(choice, choice),
                "choice": choice,
                "value": count,
                "pct": round(100 * count / total, 1),
            }
            for choice, count in (
                ("used", used),
                ("partial", partial),
                ("not_used", unused),
            )
            if count
        ],
        "by_channel_topic": by_channel_topic,
        "by_source": by_source,
        "recent": recent,
        "examples_not_used": examples,
        "relevance_buckets": buckets,
        "demo": False,
    }


def build_period_series(dialogs: Iterable[Any]) -> list[dict[str, Any]]:
    by_day_channel: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for dialog in dialogs:
        day = dialog.created_at.date().isoformat()
        by_day_channel[(day, dialog.channel or "widget")].append(dialog)

    rows: list[dict[str, Any]] = []
    for (day, channel), group in sorted(by_day_channel.items()):
        closed = [d for d in group if d.status == "closed"]
        frts = [first_response_seconds(d) for d in group]
        ahts = [aht_seconds(d) for d in closed]
        sla_flags = [within_sla(d) for d in group]
        sla_known = [flag for flag in sla_flags if flag is not None]
        ratings = [dialog_rating(d) for d in group]
        rows.append(
            {
                "date": day,
                "channel": channel,
                "channel_label": channel_label(channel),
                "sessions": len(group),
                "closed": len(closed),
                "waiting": sum(1 for d in group if d.status == "waiting"),
                "active": sum(1 for d in group if d.status == "active"),
                "avg_first_response_sec": _avg(frts),
                "avg_aht_sec": _avg(ahts),
                "sla_ok_pct": (
                    round(100 * sum(1 for f in sla_known if f) / len(sla_known), 1)
                    if sla_known
                    else None
                ),
                "avg_rating": _avg(ratings),
            }
        )
    return rows


def build_analytics_rows(
    date_from: date,
    date_to: date,
    *,
    messenger: str = "",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Daily rows compatible with cc analytics export + chat-native summary."""
    from online_chat.models import SuflerHintFeedback

    dialogs = list(dialogs_in_period(date_from, date_to, messenger=messenger))
    sufler = sufler_stats(date_from, date_to)
    by_day: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        by_day[dialog.created_at.date().isoformat()].append(dialog)

    hint_by_day: dict[str, list[Any]] = defaultdict(list)
    for fb in SuflerHintFeedback.objects.filter(
        created_at__date__gte=date_from,
        created_at__date__lte=date_to,
    ):
        hint_by_day[fb.created_at.date().isoformat()].append(fb)

    rows: list[dict[str, Any]] = []
    for day, group in sorted(by_day.items()):
        operators = sorted({(d.operator_name or "—") for d in group})
        closed = [d for d in group if d.status == "closed"]
        ahts = [aht_seconds(d) for d in closed]
        hints = hint_by_day.get(day, [])
        used = sum(1 for h in hints if h.choice == "used")
        partial = sum(1 for h in hints if h.choice == "partial")
        unused = sum(1 for h in hints if h.choice == "not_used")
        hint_total = len(hints) or 0
        useful_pct = round(100 * used / hint_total, 1) if hint_total else 0.0
        incomplete_pct = round(100 * partial / hint_total, 1) if hint_total else 0.0
        unused_pct = (
            round(100 * unused / hint_total, 1)
            if hint_total
            else (100.0 - useful_pct - incomplete_pct)
        )
        rows.append(
            {
                "date": day,
                "channel": "online_chat",
                "operator": ", ".join(operators)[:80] or "—",
                "sessions": len(group),
                "recognized_pct": 100.0,
                "avg_confidence": 1.0,
                "useful_pct": useful_pct,
                "incomplete_pct": incomplete_pct,
                "unused_pct": unused_pct,
                "incorrect_llm": unused,
                "hint_latency_p95_ms": None,
                "aht_sec": _avg(ahts) or 0,
            }
        )

    summary = {
        "sessions": len(dialogs),
        "closed": sum(1 for d in dialogs if d.status == "closed"),
        "waiting": sum(1 for d in dialogs if d.status == "waiting"),
        "active": sum(1 for d in dialogs if d.status == "active"),
        "recognized_pct": 100.0 if dialogs else 0.0,
        "avg_confidence": 1.0 if dialogs else 0.0,
        "useful_pct": sufler["used_pct"] if sufler["used_pct"] is not None else 0.0,
        "incorrect_llm": sum(
            1
            for h in SuflerHintFeedback.objects.filter(
                created_at__date__gte=date_from,
                created_at__date__lte=date_to,
                choice="not_used",
            )
        ),
        "hint_latency_p95_ms": 0,
        "avg_first_response_sec": _avg(first_response_seconds(d) for d in dialogs),
        "avg_aht_sec": _avg(aht_seconds(d) for d in dialogs if d.status == "closed"),
        "avg_rating": _avg(dialog_rating(d) for d in dialogs),
        "sla_ok_pct": (
            round(
                100
                * sum(1 for d in dialogs if within_sla(d) is True)
                / max(1, sum(1 for d in dialogs if within_sla(d) is not None)),
                1,
            )
            if any(within_sla(d) is not None for d in dialogs)
            else None
        ),
        "sufler_total": sufler["total"],
        "sufler_avg_relevance": sufler["avg_relevance"],
    }
    return rows, summary


def report_chat_period(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    series = build_period_series(dialogs)
    by_channel = Counter((d.channel or "widget") for d in dialogs)
    chart = [
        {"label": channel_label(ch), "value": count}
        for ch, count in by_channel.most_common()
    ]
    return {
        "rows": [
            {
                "date": row["date"],
                "channel": row["channel_label"],
                "sessions": row["sessions"],
                "closed": row["closed"],
                "avg_first_response_sec": row["avg_first_response_sec"],
                "sla_ok_pct": row["sla_ok_pct"],
                "avg_rating": row["avg_rating"],
            }
            for row in series
        ],
        "chart": chart
        or [{"label": d, "value": 0} for d in ("Виджет сайта", "Telegram")],
        "summary": {
            "dialogs": len(dialogs),
            "closed": sum(1 for d in dialogs if d.status == "closed"),
            "channels": len(by_channel),
        },
        "stub": False,
    }


def report_chat_sla(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    now = _utcnow()
    rows = []
    frts: list[float] = []
    waits: list[float] = []
    sla_ok = 0
    sla_total = 0
    for dialog in dialogs:
        frt = first_response_seconds(dialog)
        wait = wait_seconds(dialog, now=now)
        flag = within_sla(dialog)
        if frt is not None:
            frts.append(frt)
        if wait is not None:
            waits.append(wait)
        if flag is not None:
            sla_total += 1
            if flag:
                sla_ok += 1
        rows.append(
            {
                "ref": dialog.ref_code(),
                "client": dialog.client_display_name(),
                "channel": channel_label(dialog.channel),
                "operator": dialog.operator_name or "—",
                "status": dialog.status,
                "wait_sec": round(wait, 1) if wait is not None else None,
                "first_response_sec": round(frt, 1) if frt is not None else None,
                "sla_ok": flag,
                "created_at": dialog.created_at.isoformat(),
            }
        )
    rows.sort(key=lambda item: item["created_at"], reverse=True)
    target = get_sla_first_response_seconds()
    chart = [
        {"label": f"≤{target} с", "value": sum(1 for v in frts if v <= target)},
        {
            "label": f"{target}–{target * 2} с",
            "value": sum(1 for v in frts if target < v <= target * 2),
        },
        {
            "label": f"{target * 2}–{target * 3} с",
            "value": sum(1 for v in frts if target * 2 < v <= target * 3),
        },
        {"label": f">{target * 3} с", "value": sum(1 for v in frts if v > target * 3)},
    ]
    return {
        "rows": rows[:200],
        "chart": chart,
        "summary": {
            "sla_ok_pct": round(100 * sla_ok / sla_total, 1) if sla_total else None,
            "avg_first_response_sec": _avg(frts),
            "avg_wait_sec": _avg(waits),
            "target_sec": target,
            "answered": sla_total,
        },
        "stub": False,
    }


def report_chat_operators(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    from online_chat.models import OperatorProfile

    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    by_op: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        name = (dialog.operator_name or "").strip()
        if not name:
            continue
        by_op[name].append(dialog)

    roles = {
        p.display_name: p.role
        for p in OperatorProfile.objects.filter(display_name__in=list(by_op.keys()))
    }

    rows = []
    for name, group in sorted(by_op.items(), key=lambda item: -len(item[1])):
        closed = [d for d in group if d.status == "closed"]
        frt_flags = [within_sla(d) for d in group]
        known = [f for f in frt_flags if f is not None]
        ratings = [dialog_rating(d) for d in group]
        role = roles.get(name) or "operator"
        rows.append(
            {
                "operator": name,
                "role": role,
                "role_label": "Супервизор" if role == "supervisor" else ("Админ" if role == "admin" else "Оператор"),
                "dialogs": len(group),
                "closed": len(closed),
                "active": sum(1 for d in group if d.status == "active"),
                "avg_aht_sec": _avg(aht_seconds(d) for d in closed),
                "avg_first_response_sec": _avg(first_response_seconds(d) for d in group),
                "sla_ok_pct": (
                    round(100 * sum(1 for f in known if f) / len(known), 1) if known else None
                ),
                "avg_rating": _avg(ratings),
            }
        )
    chart = [{"label": row["operator"][:18], "value": row["dialogs"]} for row in rows[:12]]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {"operators": len(rows), "dialogs": len(dialogs)},
        "stub": False,
    }


def report_chat_ratings(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    from online_chat.models import DialogFeedback

    dialog_ids = dialogs_in_period(date_from, date_to, **filters).values_list("id", flat=True)
    feedback = list(
        DialogFeedback.objects.filter(dialog_id__in=dialog_ids).select_related("dialog")
    )
    hist = Counter(item.rating for item in feedback)
    rows = [
        {
            "rating": stars,
            "count": hist.get(stars, 0),
            "pct": round(100 * hist.get(stars, 0) / len(feedback), 1) if feedback else 0,
        }
        for stars in range(5, 0, -1)
    ]
    chart = [
        {"label": f"{stars}★", "value": hist.get(stars, 0)}
        for stars in range(1, 6)
    ]
    detail = [
        {
            "ref": item.dialog.ref_code(),
            "client": item.dialog.client_display_name(),
            "channel": channel_label(item.dialog.channel),
            "operator": item.dialog.operator_name or "—",
            "rating": item.rating,
            "comment": (item.comment or "")[:120],
            "created_at": item.created_at.isoformat(),
        }
        for item in sorted(feedback, key=lambda x: x.created_at, reverse=True)[:100]
    ]
    return {
        "rows": detail or rows,
        "chart": chart,
        "summary": {
            "ratings": len(feedback),
            "avg_rating": _avg(item.rating for item in feedback),
            "distribution": rows,
        },
        "stub": False,
    }


def report_chat_topics(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(
        dialogs_in_period(date_from, date_to, **filters).filter(status="closed")
    )
    prev_from = date_from - (date_to - date_from + timedelta(days=1))
    prev_to = date_from - timedelta(days=1)
    prev = list(
        dialogs_in_period(prev_from, prev_to, **filters).filter(status="closed")
    )
    cur_counts = Counter((d.close_topic or "").strip() or "Прочее" for d in dialogs)
    prev_counts = Counter((d.close_topic or "").strip() or "Прочее" for d in prev)
    total = sum(cur_counts.values()) or 1
    rows = []
    for topic, count in cur_counts.most_common():
        prev_count = prev_counts.get(topic, 0)
        growth = (
            round(100 * (count - prev_count) / prev_count, 1)
            if prev_count
            else (100.0 if count else 0.0)
        )
        rows.append(
            {
                "topic": topic,
                "dialogs": count,
                "share_pct": round(100 * count / total, 1),
                "growth_pct": growth,
                "prev_dialogs": prev_count,
            }
        )
    chart = [{"label": row["topic"], "value": row["dialogs"]} for row in rows[:12]]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {"topics": len(rows), "closed": len(dialogs)},
        "stub": False,
    }


def report_chat_offline(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    counts = Counter()
    for dialog in dialogs:
        if dialog.outcome:
            counts[dialog.outcome] += 1
        elif dialog.status == "blocked":
            counts["rejected"] += 1
        elif dialog.status == "closed":
            counts["resolved"] += 1
        else:
            counts[dialog.status] += 1
    rows = [
        {
            "result": OUTCOME_LABELS.get(key) or STATUS_LABELS.get(key, key),
            "count": count,
            "pct": round(100 * count / max(1, len(dialogs)), 1),
        }
        for key, count in counts.most_common()
    ]
    chart = [{"label": row["result"], "value": row["count"]} for row in rows]
    detail = [
        {
            "ref": d.ref_code(),
            "client": d.client_display_name(),
            "channel": channel_label(d.channel),
            "status": STATUS_LABELS.get(d.status, d.status),
            "result": OUTCOME_LABELS.get(d.outcome or "") or STATUS_LABELS.get(d.status, "Не определён"),
            "operator": d.operator_name or "—",
            "created_at": d.created_at.isoformat(),
        }
        for d in dialogs
        if d.outcome in {"lost", "offline", "rejected"} or d.status in {"blocked", "waiting", "active"}
    ][:100]
    return {
        "rows": detail or rows,
        "chart": chart,
        "summary": {"dialogs": len(dialogs)},
        "stub": False,
    }


def report_chat_history(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    qs = dialogs_in_period(date_from, date_to, **filters).order_by("-updated_at")[:150]
    rows = []
    status_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    for dialog in qs:
        status_counts[dialog.status] += 1
        channel_counts[channel_label(dialog.channel)] += 1
        rows.append(
            {
                "ref": dialog.ref_code(),
                "dialog_id": str(dialog.id),
                "client": dialog.client_display_name(),
                "phone": dialog.client_phone or "—",
                "operator": dialog.operator_name or "—",
                "status": STATUS_LABELS.get(dialog.status, dialog.status),
                "result": OUTCOME_LABELS.get(dialog.outcome or "", "Не определён"),
                "topic": dialog.close_topic or "—",
                "channel": channel_label(dialog.channel),
                "created_at": dialog.created_at.isoformat(),
                "closed_at": dialog.closed_at.isoformat() if dialog.closed_at else "",
                "messages": dialog.messages.count(),
                "rating": dialog_rating(dialog),
                "summary": (dialog.summary_short or "")[:200],
            }
        )
    chart = [
        {"label": STATUS_LABELS.get(key, key), "value": count}
        for key, count in status_counts.most_common()
    ] or [
        {"label": label, "value": count}
        for label, count in channel_counts.most_common()
    ]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {"rows": len(rows)},
        "stub": False,
    }


def report_usefulness(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    stats = sufler_stats(date_from, date_to, source=_sufler_source_filter(filters))
    rows = stats.get("by_source") or []
    if not rows and stats["total"]:
        rows = [
            {
                "channel": "chat",
                "label": "Все каналы",
                "useful_pct": stats["used_pct"] or 0,
                "incomplete_pct": stats["partial_pct"] or 0,
                "unused_pct": stats["unused_pct"] or 0,
                "sessions": stats["total"],
                "avg_relevance": stats["avg_relevance"],
            }
        ]
    chart = [
        {"label": item["label"], "value": item["value"], "pct": item["pct"]}
        for item in stats["by_choice"]
    ]
    return {
        "rows": rows if stats["total"] else [],
        "chart": chart,
        "summary": {
            "total": stats["total"],
            "used_pct": stats["used_pct"],
            "avg_relevance": stats["avg_relevance"],
        },
        "stub": bool(stats.get("demo")),
    }


def report_relevance(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    stats = sufler_stats(date_from, date_to, source=_sufler_source_filter(filters))
    raw_rows = stats["by_channel_topic"]
    group_by = (filters.get("group_by") or "channel").strip().lower()

    rows = [
        {
            "channel": row["channel_label"],
            "channel_label": row["channel_label"],
            "topic": row["topic"],
            "avg_relevance": row["avg_relevance"],
            "answers": row["answers"],
            "used_pct": row["used_pct"],
        }
        for row in raw_rows
    ]

    if group_by == "topic":
        by_topic: dict[str, list[float]] = defaultdict(list)
        for row in raw_rows:
            if row["avg_relevance"] is not None:
                by_topic[row["topic"]].append(float(row["avg_relevance"]))
        chart = [
            {
                "label": topic[:24],
                "value": round(mean(rels), 1),
            }
            for topic, rels in sorted(by_topic.items(), key=lambda x: -len(x[1]))[:12]
            if rels
        ]
        agg_rows = [
            {
                "topic": topic,
                "avg_relevance": round(mean(rels), 1),
                "answers": len(rels),
            }
            for topic, rels in sorted(by_topic.items(), key=lambda x: -len(x[1]))
        ]
        rows = agg_rows or rows
    elif group_by in {"", "none"}:
        bucket_chart = _relevance_bucket_chart(stats.get("relevance_buckets") or {})
        rels = [
            float(row["avg_relevance"])
            for row in raw_rows
            if row["avg_relevance"] is not None
        ]
        avg = round(mean(rels), 1) if rels else 0
        chart = bucket_chart or [{"label": "Средняя релевантность", "value": avg}]
        rows = [{"avg_relevance": avg, "answers": stats["total"]}] if rels else rows
    else:
        by_channel: dict[str, list[float]] = defaultdict(list)
        for row in raw_rows:
            label = row["channel_label"]
            if row["avg_relevance"] is not None:
                by_channel[label].append(float(row["avg_relevance"]))
        chart = [
            {"label": label, "value": round(mean(rels), 1)}
            for label, rels in sorted(by_channel.items(), key=lambda x: x[0])
            if rels
        ]
        agg_rows = [
            {
                "channel": label,
                "avg_relevance": round(mean(rels), 1),
                "answers": len(rels),
            }
            for label, rels in sorted(by_channel.items(), key=lambda x: -len(x[1]))
        ]
        rows = agg_rows or rows

    return {
        "rows": rows,
        "chart": chart,
        "summary": {"answers": stats["total"], "avg_relevance": stats["avg_relevance"]},
        "stub": bool(stats.get("demo")),
    }


def report_correctness(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    stats = sufler_stats(date_from, date_to, source=_sufler_source_filter(filters))
    rows = [
        {
            "mark": row["label"],
            "value": row["value"],
            "pct": row["pct"],
        }
        for row in stats["by_choice"]
    ]
    chart = [{"label": row["mark"], "value": row["pct"]} for row in rows]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {"total": stats["total"]},
        "stub": bool(stats.get("demo")),
    }


def report_performance(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    by_day: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        by_day[dialog.created_at.date().isoformat()].append(dialog)
    rows = []
    for day, group in sorted(by_day.items()):
        frts = [v for v in (first_response_seconds(d) for d in group) if v is not None]
        ahts = [v for v in (aht_seconds(d) for d in group if d.status == "closed") if v is not None]
        rows.append(
            {
                "date": day,
                "dialogs": len(group),
                "avg_first_response_sec": _avg(frts),
                "aht_sec": _avg(ahts),
            }
        )
    chart = [
        {"label": row["date"][5:], "value": row["avg_first_response_sec"] or 0}
        for row in rows
    ]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {
            "avg_aht_sec": _avg(aht_seconds(d) for d in dialogs if d.status == "closed"),
            "avg_first_response_sec": _avg(
                v for v in (first_response_seconds(d) for d in dialogs) if v is not None
            ),
        },
        "stub": not dialogs,
    }


def report_errors(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    stats = sufler_stats(date_from, date_to, source=_sufler_source_filter(filters))
    rows = [
        {
            "operator": row.get("operator") or "—",
            "example": row.get("example") or "—",
            "relevance_pct": row.get("relevance_pct"),
            "at": row.get("at") or "",
            "reason": row.get("reason") or "Не воспользовался",
            "channel": channel_label(row.get("channel") or "widget"),
        }
        for row in stats["examples_not_used"]
    ]
    reason_counts = Counter(row["reason"] for row in rows)
    aggregated = [
        {
            "reason": reason,
            "count": count,
            "example": next(r["example"] for r in rows if r["reason"] == reason),
            "channel": next((r["channel"] for r in rows if r["reason"] == reason), "—"),
        }
        for reason, count in reason_counts.most_common()
    ]
    by_operator = Counter(row["operator"] for row in rows)
    chart = (
        [{"label": r["reason"][:28], "value": r["count"]} for r in aggregated]
        or [
            {"label": name, "value": count}
            for name, count in by_operator.most_common(12)
        ]
    )
    return {
        "rows": aggregated or rows,
        "chart": chart,
        "summary": {"cases": len(rows)},
        "stub": bool(stats.get("demo")),
    }


def report_repeats(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    from online_chat.models import normalize_phone

    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    by_client: dict[str, list[Any]] = defaultdict(list)
    for dialog in dialogs:
        phone = normalize_phone(dialog.client_phone)
        external = (dialog.client_external_id or "").strip()
        key = phone or external or f"name:{dialog.client_display_name().casefold()}"
        by_client[key].append(dialog)

    rows = []
    for key, group in by_client.items():
        if len(group) < 2:
            continue
        topics = Counter((d.close_topic or "Прочее") for d in group)
        channels = sorted({channel_label(d.channel) for d in group})
        sample = group[0]
        rows.append(
            {
                "client": sample.client_display_name(),
                "phone": sample.client_phone or key[:16],
                "topic": topics.most_common(1)[0][0],
                "repeats": len(group),
                "channels": " → ".join(channels),
            }
        )
    rows.sort(key=lambda item: -item["repeats"])
    chart = [
        {"label": row["topic"][:20], "value": row["repeats"]}
        for row in rows[:12]
    ]
    clients = len(by_client)
    repeat_clients = len(rows)
    return {
        "rows": rows[:100],
        "chart": chart,
        "summary": {
            "clients": clients,
            "repeat_clients": repeat_clients,
            "repeat_pct": round(100 * repeat_clients / clients, 1) if clients else 0,
        },
        "stub": False,
    }


def report_executive(date_from: date, date_to: date, **filters: Any) -> dict[str, Any]:
    dialogs = list(dialogs_in_period(date_from, date_to, **filters))
    sufler = sufler_stats(date_from, date_to)
    closed = [d for d in dialogs if d.status == "closed"]
    ratings = [dialog_rating(d) for d in dialogs]
    sla_known = [within_sla(d) for d in dialogs]
    sla_vals = [f for f in sla_known if f is not None]
    by_channel = Counter(channel_label(d.channel) for d in dialogs)
    rows = [
        {
            "metric": "Обращений всего",
            "online_chat": len(dialogs),
            "telephony": "—",
            "total": len(dialogs),
        },
        {
            "metric": "Закрыто",
            "online_chat": len(closed),
            "telephony": "—",
            "total": len(closed),
        },
        {
            "metric": "Соблюдение SLA первого ответа, %",
            "online_chat": (
                round(100 * sum(1 for f in sla_vals if f) / len(sla_vals), 1)
                if sla_vals
                else "—"
            ),
            "telephony": "—",
            "total": (
                round(100 * sum(1 for f in sla_vals if f) / len(sla_vals), 1)
                if sla_vals
                else "—"
            ),
        },
        {
            "metric": "Средняя оценка клиента",
            "online_chat": _avg(ratings) if ratings else "—",
            "telephony": "—",
            "total": _avg(ratings) if ratings else "—",
        },
        {
            "metric": "Полезность суфлёра «воспользовался», %",
            "online_chat": sufler["used_pct"] if sufler["used_pct"] is not None else "—",
            "telephony": "—",
            "total": sufler["used_pct"] if sufler["used_pct"] is not None else "—",
        },
        {
            "metric": "Средняя релевантность подсказок, %",
            "online_chat": sufler["avg_relevance"] if sufler["avg_relevance"] is not None else "—",
            "telephony": "—",
            "total": sufler["avg_relevance"] if sufler["avg_relevance"] is not None else "—",
        },
        {
            "metric": "Среднее время обработки, с",
            "online_chat": _avg(aht_seconds(d) for d in closed) or "—",
            "telephony": "—",
            "total": _avg(aht_seconds(d) for d in closed) or "—",
        },
    ]
    chart = [{"label": ch, "value": count} for ch, count in by_channel.most_common()]
    return {
        "rows": rows,
        "chart": chart,
        "summary": {"dialogs": len(dialogs), "sufler": sufler["total"]},
        "stub": False,
    }


def build_live_dashboard() -> dict[str, Any]:
    from online_chat.models import Department, Dialog, OperatorProfile, SuflerHintFeedback

    now = dj_tz.now()
    today = now.date()
    waiting_qs = Dialog.objects.filter(status=Dialog.Status.WAITING)
    active_qs = Dialog.objects.filter(status=Dialog.Status.ACTIVE)
    waiting = waiting_qs.count()
    active = active_qs.count()
    closed_today = Dialog.objects.filter(
        status=Dialog.Status.CLOSED,
        closed_at__date=today,
    ).count()

    wait_samples = [
        wait_seconds(d, now=now)
        for d in waiting_qs.only("created_at", "accepted_at", "status")[:500]
    ]
    answered = list(
        Dialog.objects.filter(
            first_response_at__isnull=False,
            created_at__gte=now - timedelta(days=1),
        ).only("created_at", "first_response_at")[:2000]
    )
    sla_flags = [within_sla(d) for d in answered]
    sla_known = [f for f in sla_flags if f is not None]

    departments = []
    for dept in Department.objects.filter(is_active=True).order_by("priority", "name")[:20]:
        departments.append(
            {
                "name": dept.name,
                "active": Dialog.objects.filter(
                    status=Dialog.Status.ACTIVE, department=dept
                ).count(),
                "queue": Dialog.objects.filter(
                    status=Dialog.Status.WAITING, department=dept
                ).count(),
            }
        )
    if not departments:
        # Fallback grouping by channel when departments not configured.
        for channel, label in CHANNEL_LABELS.items():
            a = Dialog.objects.filter(status=Dialog.Status.ACTIVE, channel=channel).count()
            q = Dialog.objects.filter(status=Dialog.Status.WAITING, channel=channel).count()
            if a or q:
                departments.append({"name": label, "active": a, "queue": q})

    operators = []
    active_by_name = Counter(
        Dialog.objects.filter(status=Dialog.Status.ACTIVE)
        .exclude(operator_name="")
        .values_list("operator_name", flat=True)
    )
    profiles = {
        p.display_name: p
        for p in OperatorProfile.objects.filter(is_active=True)[:200]
    }
    names = set(active_by_name) | set(profiles)
    for name in sorted(names, key=lambda n: (-active_by_name.get(n, 0), n))[:40]:
        profile = profiles.get(name)
        operators.append(
            {
                "name": name,
                "status": profile.presence if profile else ("online" if active_by_name.get(name) else "offline"),
                "active_dialogs": active_by_name.get(name, 0),
                "channel": "online_chat",
            }
        )

    operators_online = sum(
        1
        for op in operators
        if op["status"] in {"online", "busy"} or op["active_dialogs"] > 0
    )
    if not operators_online:
        operators_online = sum(1 for op in operators if op["active_dialogs"] > 0)

    # Alerts from real thresholds (FR-RPT-CC-06 lite)
    alerts: list[dict[str, Any]] = []
    avg_wait = _avg(wait_samples)
    if waiting and avg_wait is not None and avg_wait > 180:
        alerts.append(
            {
                "id": "wait-sla",
                "tone": "warning",
                "title": "Ожидание в очереди > 3 мин",
                "detail": f"Сейчас в очереди {waiting}, среднее ожидание {int(avg_wait)} с",
                "at": now.isoformat(),
            }
        )
    topic_stats = report_chat_topics(today - timedelta(days=6), today)
    for row in topic_stats["rows"][:3]:
        if (row.get("growth_pct") or 0) >= 30 and row.get("dialogs", 0) >= 3:
            alerts.append(
                {
                    "id": f"topic-{row['topic'][:24]}",
                    "tone": "info",
                    "title": f"Рост тематики «{row['topic']}» +{row['growth_pct']}%",
                    "detail": f"{row['dialogs']} закрытий за 7 дней",
                    "at": now.isoformat(),
                }
            )

    feed = []
    for dialog in (
        Dialog.objects.exclude(status=Dialog.Status.BLOCKED)
        .select_related("feedback")
        .order_by("-updated_at")[:40]
    ):
        feed.append(
            {
                "id": str(dialog.id),
                "ref": dialog.ref_code(),
                "channel": channel_label(dialog.channel),
                "messenger": dialog.channel or "widget",
                "operator": dialog.operator_name or "—",
                "client": dialog.client_display_name(),
                "topic": dialog.close_topic or "—",
                "status": dialog.status,
                "wait_sec": wait_seconds(dialog, now=now),
                "relevance_pct": None,
                "feedback": (
                    f"{dialog_rating(dialog)}★"
                    if dialog_rating(dialog) is not None
                    else "—"
                ),
                "preview": (dialog.preview or dialog.summary_short or "")[:120],
                "at": dialog.updated_at.isoformat(),
            }
        )

    # Enrich feed with latest sufler feedback relevance when available
    recent_hints = {
        str(fb.dialog_id): fb
        for fb in SuflerHintFeedback.objects.exclude(dialog=None)
        .order_by("-created_at")[:80]
    }
    for item in feed:
        fb = recent_hints.get(item["id"])
        if fb:
            item["relevance_pct"] = fb.relevance_percent
            if item["feedback"] == "—":
                item["feedback"] = FEEDBACK_LABELS.get(fb.choice, fb.choice)

    llm_feed = []
    for fb in SuflerHintFeedback.objects.select_related("dialog").order_by("-created_at")[:30]:
        llm_feed.append(
            {
                "id": str(fb.id),
                "channel": channel_label(getattr(fb.dialog, "channel", None) or "widget"),
                "operator": fb.operator_name or "—",
                "topic": (getattr(fb.dialog, "close_topic", None) or "—"),
                "relevance_pct": fb.relevance_percent or 0,
                "feedback": fb.choice,
                "latency_ms": 0,
                "at": fb.created_at.isoformat(),
                "query": (fb.query or "")[:120],
            }
        )

    has_data = bool(waiting or active or closed_today or feed)
    return {
        "generated_at": now.isoformat(),
        "stub": not has_data,
        "source": "Онлайн-чат",
        "kpis": {
            "in_progress": active,
            "in_queue": waiting,
            "avg_wait_sec": int(avg_wait) if avg_wait is not None else 0,
            "operators_online": operators_online,
            "sla_ok_pct": (
                round(100 * sum(1 for f in sla_known if f) / len(sla_known), 1)
                if sla_known
                else 0
            ),
            "hint_p95_ms": 0,
            "closed_today": closed_today,
        },
        "departments": departments,
        "operators": operators,
        "alerts": alerts,
        "llm_feed": llm_feed,
        "dialog_feed": feed,
        "chat": {
            "waiting": waiting,
            "active": active,
            "closed_today": closed_today,
            "operators_from_chat": [
                {"name": op["name"], "active_dialogs": op["active_dialogs"]}
                for op in operators
                if op["active_dialogs"]
            ],
        },
    }


def builder_metric_value(
    metric_id: str,
    date_from: date,
    date_to: date,
) -> tuple[float | int | None, str]:
    dialogs = list(dialogs_in_period(date_from, date_to))
    sufler = sufler_stats(date_from, date_to)
    closed = [d for d in dialogs if d.status == "closed"]
    if metric_id == "dialogs_total":
        return len(dialogs), ""
    if metric_id == "dialogs_closed":
        return len(closed), ""
    if metric_id == "sla_pct":
        known = [within_sla(d) for d in dialogs]
        vals = [f for f in known if f is not None]
        return (
            (round(100 * sum(1 for f in vals if f) / len(vals), 1) if vals else None),
            "%",
        )
    if metric_id in {"aht", "aht_sec"}:
        return _avg(aht_seconds(d) for d in closed), "с"
    if metric_id == "csat":
        return _avg(dialog_rating(d) for d in dialogs), ""
    if metric_id in {"useful_pct", "sufler_used_pct"}:
        return sufler["used_pct"], "%"
    if metric_id == "relevance_avg":
        return sufler["avg_relevance"], "%"
    if metric_id == "incorrect_llm":
        return sufler["unused_pct"], "%"
    if metric_id == "avg_first_response_sec":
        frts = [v for v in (first_response_seconds(d) for d in dialogs) if v is not None]
        return _avg(frts), "с"
    if metric_id == "topics_top":
        topics = report_chat_topics(date_from, date_to)
        top = topics["rows"][0]["topic"] if topics["rows"] else "—"
        return len(topics["rows"]), top
    return None, ""
