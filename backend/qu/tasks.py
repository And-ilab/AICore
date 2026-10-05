"""FR-UND-08 QU retraining task and ``reindex.completed`` integration.

Flow:
    Sufler ingest -> reindex_kb -> qu_retrain.

Batch and manual reindex implementations may emit ``reindex.completed`` to
enqueue the same retraining task.

The deterministic task id is a correlation/idempotency key for P3-02. Celery
does not deduplicate tasks merely because task IDs match; production P3-02
must add a Redis/database lock and merge repeated events during the 60-second
debounce window described by FR-UND-08.
"""

from __future__ import annotations

import hashlib
from typing import Any

from celery import shared_task
from django.dispatch import Signal, receiver


REINDEX_COMPLETED_EVENT = "reindex.completed"
QU_RETRAIN_DEBOUNCE_SECONDS = 60
reindex_completed = Signal()


def _required_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def build_retrain_task_id(
    kb_id: str,
    reindex_job_id: str,
    content_version: str,
) -> str:
    """Build a stable, broker-safe correlation ID for one index version."""
    raw_key = "\x1f".join(
        (
            _required_string("kb_id", kb_id),
            _required_string("reindex_job_id", reindex_job_id),
            _required_string("content_version", content_version),
        )
    )
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return f"qu-retrain-{digest}"


@shared_task(name="qu.qu_retrain")
def qu_retrain(
    reindex_result: dict[str, Any] | None = None,
    *,
    kb_id: str | None = None,
    reindex_job_id: str | None = None,
    content_version: str | None = None,
    trigger: str = REINDEX_COMPLETED_EVENT,
) -> dict[str, str]:
    """Run the QU retraining contract after a successful index update."""
    if reindex_result is not None:
        if reindex_result.get("outcome") not in {
            "indexed",
            "soft_deleted",
            "hard_deleted",
        }:
            return {
                "status": "skipped",
                "kb_id": _required_string(
                    "kb_id",
                    reindex_result.get("kb_id"),
                ),
                "reindex_job_id": _required_string(
                    "reindex_job_id",
                    reindex_result.get("reindex_job_id"),
                ),
                "content_version": _required_string(
                    "content_version",
                    reindex_result.get("content_version"),
                ),
                "trigger": _required_string(
                    "trigger",
                    reindex_result.get("trigger", trigger),
                ),
            }
        kb_id = reindex_result.get("kb_id")
        reindex_job_id = reindex_result.get("reindex_job_id")
        content_version = reindex_result.get("content_version")
        trigger = reindex_result.get("trigger", trigger)

    return {
        "status": "completed",
        "kb_id": _required_string("kb_id", kb_id),
        "reindex_job_id": _required_string(
            "reindex_job_id",
            reindex_job_id,
        ),
        "content_version": _required_string(
            "content_version",
            content_version,
        ),
        "trigger": _required_string("trigger", trigger),
    }


@receiver(
    reindex_completed,
    dispatch_uid="qu.enqueue_retrain_on_reindex_completed",
)
def enqueue_retrain_on_reindex_completed(
    sender: Any,
    *,
    kb_id: str,
    reindex_job_id: str,
    content_version: str,
    **_kwargs: Any,
) -> Any:
    """Enqueue QU retraining after a committed, searchable index update."""
    validated_kb_id = _required_string("kb_id", kb_id)
    validated_job_id = _required_string(
        "reindex_job_id",
        reindex_job_id,
    )
    validated_content_version = _required_string(
        "content_version",
        content_version,
    )
    task_id = build_retrain_task_id(
        validated_kb_id,
        validated_job_id,
        validated_content_version,
    )
    return qu_retrain.apply_async(
        kwargs={
            "kb_id": validated_kb_id,
            "reindex_job_id": validated_job_id,
            "content_version": validated_content_version,
            "trigger": REINDEX_COMPLETED_EVENT,
        },
        countdown=QU_RETRAIN_DEBOUNCE_SECONDS,
        task_id=task_id,
        headers={
            "event_type": REINDEX_COMPLETED_EVENT,
            "sender": getattr(sender, "__name__", str(sender)),
        },
    )
