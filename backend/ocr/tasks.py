"""Celery tasks for IV.5 OCR processing."""

from __future__ import annotations

from typing import Any

from celery import shared_task

from ocr.pipeline import OcrPipelineError, process_job


@shared_task(
    name="ocr.run_ocr_job",
    bind=True,
    max_retries=2,
    default_retry_delay=5,
)
def run_ocr_job(self, job_id: str) -> dict[str, Any]:
    """Recognize uploaded document and store OCR JSON in object storage."""
    try:
        return process_job(job_id)
    except OcrPipelineError:
        # Permanent validation / missing job — do not retry.
        raise
    except Exception as exc:  # noqa: BLE001 — retry transient store/engine faults
        raise self.retry(exc=exc) from exc
