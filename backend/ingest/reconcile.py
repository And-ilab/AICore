"""INT-09 reconciliation: poll Bitrix /changes and enqueue Model B events."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from django.db import transaction
from django.utils.dateparse import parse_datetime

from ingest.bitrix_client import BitrixClientError, get_bitrix_changes_client
from ingest.models import KnowledgeIngestEvent, SuzReconcileState
from ingest.schema import SuzPayload, SuzPayloadError
from ingest.tasks import enqueue_ingest_chain


DEFAULT_CURSOR = "1970-01-01T00:00:00+00:00"


def _normalize_cursor(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return DEFAULT_CURSOR
    parsed = parse_datetime(text.replace("Z", "+00:00"))
    if parsed is None:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


def get_or_create_state() -> SuzReconcileState:
    state, _ = SuzReconcileState.objects.get_or_create(
        pk=1,
        defaults={"cursor": DEFAULT_CURSOR},
    )
    return state


def run_reconciliation(*, limit: int = 100) -> dict[str, Any]:
    """
    Poll Bitrix outbox tail (Model B INT-09) and process events as webhooks.

    Events already stored by event_id are skipped (idempotent with INT-08).
    """
    state = get_or_create_state()
    since = _normalize_cursor(state.cursor)
    client = get_bitrix_changes_client()

    try:
        page = client.fetch_changes(since, limit=limit)
    except BitrixClientError as exc:
        state.last_error = str(exc)[:2000]
        state.last_run_at = datetime.now(timezone.utc)
        state.save(update_fields=["last_error", "last_run_at", "updated_at"])
        return {
            "status": "error",
            "acceptance": ["INT-T-SUZ", "INT-09"],
            "cursor": since,
            "error": str(exc),
            "accepted": 0,
            "skipped": 0,
            "failed": 0,
        }

    accepted = 0
    skipped = 0
    failed = 0
    failures: list[dict[str, str]] = []

    for raw_event in page.events:
        event_id = str(raw_event.get("event_id") or "")
        if (
            event_id
            and KnowledgeIngestEvent.objects.filter(event_id=event_id).exists()
        ):
            skipped += 1
            continue
        try:
            SuzPayload.from_mapping(raw_event)
            enqueue_ingest_chain(raw_event)
            accepted += 1
        except (SuzPayloadError, Exception) as exc:  # noqa: BLE001
            failed += 1
            failures.append(
                {
                    "event_id": event_id or "unknown",
                    "error": str(exc)[:300],
                }
            )

    with transaction.atomic():
        state.cursor = _normalize_cursor(page.cursor) or since
        state.last_run_at = datetime.now(timezone.utc)
        state.last_error = ""
        state.last_accepted = accepted
        state.last_skipped = skipped
        state.last_failed = failed
        state.save()

    return {
        "status": "ok",
        "acceptance": ["INT-T-SUZ", "INT-09"],
        "cursor": state.cursor,
        "events_fetched": len(page.events),
        "accepted": accepted,
        "skipped": skipped,
        "failed": failed,
        "failures": failures[:20],
        "mode": "model_b_polling_fallback",
    }
