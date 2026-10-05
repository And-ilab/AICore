"""Celery orchestration for FR-UND-08 knowledge-base updates + INT-09 reconcile."""

from __future__ import annotations

from typing import Any, Mapping

from celery import chain, shared_task
from celery.result import AsyncResult
from django.conf import settings

from ingest.pipeline import INDEX_NAME, ingest_payload
from ingest.schema import SuzPayload
from qu.tasks import (
    QU_RETRAIN_DEBOUNCE_SECONDS,
    REINDEX_COMPLETED_EVENT,
    build_retrain_task_id,
    qu_retrain,
)


@shared_task(name="ingest.reindex_kb")
def reindex_kb(payload_data: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize, embed, and commit one SUZ article event to the KB index."""
    payload = SuzPayload.from_mapping(payload_data)
    result = ingest_payload(payload)
    return {
        "status": result.status,
        "outcome": result.outcome,
        "chunks_indexed": result.chunks_indexed,
        "kb_id": INDEX_NAME,
        "reindex_job_id": str(payload.event_id),
        "content_version": str(payload.version_id or payload.event_id),
        "trigger": REINDEX_COMPLETED_EVENT,
    }


@shared_task(name="ingest.reconcile_suz_changes")
def reconcile_suz_changes(limit: int | None = None) -> dict[str, Any]:
    """INT-09 Model B polling fallback: GET Bitrix /changes and ingest events."""
    from ingest.reconcile import run_reconciliation

    page_limit = limit
    if page_limit is None:
        page_limit = int(getattr(settings, "SUZ_RECONCILE_LIMIT", 100))
    return run_reconciliation(limit=page_limit)


@shared_task(name="ingest.crawl_assistant_website")
def crawl_assistant_website(job_id: int) -> dict[str, Any]:
    """P5-07: crawl a website source into assistant_* RAG. Not called from chat."""
    from hub.website_crawl import run_website_crawl

    return run_website_crawl(job_id)


def enqueue_ingest_chain(payload_data: Mapping[str, Any]) -> AsyncResult:
    """Enqueue reindexing followed by debounced QU retraining."""
    payload = SuzPayload.from_mapping(payload_data)
    retrain_task_id = build_retrain_task_id(
        INDEX_NAME,
        str(payload.event_id),
        str(payload.version_id or payload.event_id),
    )
    workflow = chain(
        reindex_kb.s(dict(payload_data)),
        qu_retrain.s().set(
            countdown=QU_RETRAIN_DEBOUNCE_SECONDS,
            task_id=retrain_task_id,
        ),
    )
    return workflow.apply_async()
