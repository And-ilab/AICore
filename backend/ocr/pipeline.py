"""IV.5 / IV.8 OCR pipeline: upload → OCR → structure → validate → store."""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import PurePosixPath
from typing import Any, BinaryIO

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ocr.archives import ArchiveError, extract_archive, is_archive_filename
from ocr.engine import OcrEngineError, recognize_document, resolve_ocr_model
from ocr.models import OcrJob
from ocr.storage import ObjectStoreError, get_object_store
from ocr.extraction import is_open_ended_doc_type
from ocr.structuring import structure_document
from ocr.validation import ValidationRequestError, validate_document

ALLOWED_EXTENSIONS = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
)
CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}


class OcrPipelineError(ValueError):
    """Invalid OCR upload or job request."""


def _new_ids() -> tuple[str, str]:
    return (
        f"ocrjob-{uuid.uuid4().hex}",
        f"doc-{uuid.uuid4().hex}",
    )


def _normalize_filename(name: str) -> str:
    base = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not base or base in {".", ".."}:
        raise OcrPipelineError("filename is required")
    return base[:240]


def validate_upload(filename: str, size: int) -> tuple[str, str]:
    safe_name = _normalize_filename(filename)
    suffix = PurePosixPath(safe_name).suffix.casefold()
    if suffix not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise OcrPipelineError(
            f"Unsupported format {suffix or '(none)'}; allowed: {allowed}"
        )
    max_bytes = int(getattr(settings, "OCR_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
    if size <= 0:
        raise OcrPipelineError("empty file")
    if size > max_bytes:
        raise OcrPipelineError(f"file exceeds max size of {max_bytes} bytes")
    return safe_name, CONTENT_TYPES[suffix]


def create_job_from_upload(
    upload: BinaryIO,
    *,
    filename: str,
    content_type: str = "",
    created_by: str = "",
    document_type_hint: str = "",
    run_inline: bool = False,
    batch_id: str = "",
    source_archive: str = "",
    user_template_id: int | None = None,
) -> OcrJob:
    """Persist original to object storage and enqueue (or run) OCR job."""
    raw = upload.read()
    safe_name, detected_type = validate_upload(filename, len(raw))
    ctype = (content_type or "").strip() or detected_type
    sha256 = hashlib.sha256(raw).hexdigest()
    job_id, document_id = _new_ids()
    original_key = f"originals/{document_id}/{safe_name}"
    result_key = f"results/{job_id}/ocr_result.json"

    try:
        model_info = resolve_ocr_model()
        store = get_object_store()
        store.put_bytes(original_key, raw, content_type=ctype)
    except (OcrEngineError, ObjectStoreError) as exc:
        raise OcrPipelineError(str(exc)) from exc

    with transaction.atomic():
        job = OcrJob.objects.create(
            job_id=job_id,
            document_id=document_id,
            status=OcrJob.STATUS_QUEUED,
            filename=safe_name,
            content_type=ctype,
            sha256=sha256,
            original_object_key=original_key,
            result_object_key=result_key,
            ocr_model=model_info["model"],
            document_type=(document_type_hint or "")[:64],
            created_by=created_by[:150],
            batch_id=(batch_id or "")[:64],
            source_archive=(source_archive or "")[:255],
            user_template_id=user_template_id,
        )

    if run_inline:
        try:
            process_job(job.job_id)
        except Exception as exc:
            job.refresh_from_db()
            if job.status != OcrJob.STATUS_ERROR:
                raise OcrPipelineError(str(exc)) from exc
            raise OcrPipelineError(job.error_message or str(exc)) from exc
        job.refresh_from_db()
        return job

    if getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        process_job(job.job_id)
        job.refresh_from_db()
        return job

    from ocr.tasks import run_ocr_job

    run_ocr_job.delay(job.job_id)
    return job


def create_jobs_from_upload(
    upload: BinaryIO,
    *,
    filename: str,
    content_type: str = "",
    created_by: str = "",
    document_type_hint: str = "",
    run_inline: bool = False,
    user_template_id: int | None = None,
) -> dict[str, Any]:
    """Create one job, or one job per ZIP/RAR member (IV.3 queue)."""
    raw = upload.read()
    safe_name = _normalize_filename(filename)
    if is_archive_filename(safe_name):
        max_bytes = int(getattr(settings, "OCR_MAX_UPLOAD_BYTES", 25 * 1024 * 1024))
        archive_cap = int(
            getattr(settings, "OCR_ARCHIVE_MAX_UPLOAD_BYTES", max_bytes * 4)
        )
        if len(raw) <= 0:
            raise OcrPipelineError("empty file")
        if len(raw) > archive_cap:
            raise OcrPipelineError(f"file exceeds max size of {archive_cap} bytes")
        try:
            members = extract_archive(raw, safe_name)
        except ArchiveError as exc:
            raise OcrPipelineError(str(exc)) from exc
        batch_id = f"ocrbatch-{uuid.uuid4().hex}"
        jobs: list[OcrJob] = []
        from io import BytesIO

        for member in members:
            jobs.append(
                create_job_from_upload(
                    BytesIO(member.data),
                    filename=member.filename,
                    content_type=member.content_type,
                    created_by=created_by,
                    document_type_hint=document_type_hint,
                    run_inline=run_inline,
                    batch_id=batch_id,
                    source_archive=safe_name,
                    user_template_id=user_template_id,
                )
            )
        return {
            "jobs": jobs,
            "batch_id": batch_id,
            "archive": safe_name,
            "skipped": [],
        }

    from io import BytesIO

    job = create_job_from_upload(
        BytesIO(raw),
        filename=safe_name,
        content_type=content_type,
        created_by=created_by,
        document_type_hint=document_type_hint,
        run_inline=run_inline,
        user_template_id=user_template_id,
    )
    return {
        "jobs": [job],
        "batch_id": "",
        "archive": "",
        "skipped": [],
    }


def _attach_structuring(
    result: dict[str, Any],
    *,
    filename: str,
    document_type_hint: str = "",
    user_template: Any | None = None,
) -> dict[str, Any]:
    pages = result.get("pages") or []
    page_texts = [
        str(page.get("text") or "") for page in pages if isinstance(page, dict)
    ]
    ocr_text = "\n\n".join(page_texts)
    schema = None
    user_schema_keys: list[str] = []
    if user_template is not None:
        from ocr.user_templates import field_schema_for, schema_keys

        schema = field_schema_for(user_template)
        user_schema_keys = schema_keys(user_template)
    hint_raw = "" if user_template is not None else (document_type_hint or "").strip()
    open_ended = is_open_ended_doc_type(hint_raw)
    extract_hint = None if open_ended else hint_raw
    if extract_hint and schema is None:
        try:
            from ocr.templates_registry import template_schema_for

            schema = template_schema_for(extract_hint)
        except Exception:
            schema = None

    structured = structure_document(
        ocr_text,
        filename=filename,
        document_type_hint=extract_hint,
        field_schema=schema,
        use_gateway=True,
        pages=page_texts,
    )
    doc_type = structured["document_type"]
    fields = structured["fields"]

    if hint_raw.lower() in {"ml", "auto"}:
        doc_type = "ml"
    elif extract_hint:
        doc_type = extract_hint

    known_fields = dict(fields)
    if user_schema_keys:
        known_fields = {}
        for key in user_schema_keys:
            payload = fields.get(key)
            if payload is None:
                known_fields[key] = {"value": "", "confidence": 0}
            else:
                known_fields[key] = payload
    elif not open_ended and doc_type and doc_type != "unknown":
        try:
            from ocr.templates_registry import template_schema_for
            from ocr.validation import _load_rules, DEFAULT_RULES_PATH

            org_schema_keys = set((template_schema_for(doc_type).get("fields") or {}).keys())
        except Exception:
            try:
                from ocr.validation import DEFAULT_RULES_PATH, _load_rules

                yaml_spec = _load_rules(DEFAULT_RULES_PATH)["document_types"].get(
                    doc_type
                ) or {}
                org_schema_keys = set((yaml_spec.get("fields") or {}).keys())
            except Exception:
                org_schema_keys = set()
        if org_schema_keys:
            known_fields = {
                key: value for key, value in fields.items() if key in org_schema_keys
            }

    validation_payload: dict[str, Any] | None = None
    if user_schema_keys:
        validation_payload = None
        doc_type = ""
    elif not open_ended and doc_type and doc_type != "unknown" and known_fields:
        try:
            validated = validate_document(
                doc_type,
                known_fields,
                job_id=result.get("job_id"),
                document_id=result.get("document_id"),
                document_sha256=result.get("document_sha256"),
            )
            validation_payload = validated.as_dict()
        except (ValidationRequestError, Exception) as exc:
            validation_payload = {
                "status": "pending_review",
                "error": str(exc),
                "fields": known_fields,
            }

    try:
        from ocr.page_templates import detect_page_kind

        result["page_kinds"] = [detect_page_kind(text) for text in page_texts]
    except Exception:
        result["page_kinds"] = []

    result["document_type_candidate"] = doc_type
    result["document_type"] = doc_type
    result["fields"] = known_fields if (extract_hint or user_schema_keys) else fields
    if user_template is not None:
        result["user_template_id"] = user_template.id
        result["user_template_name"] = user_template.name
    result["field_count"] = len(fields)
    result["llm_proposal"] = structured.get("llm_proposal")
    result["validation"] = (
        validation_payload.get("validation")
        if validation_payload
        else {"status": "pending_review", "downstream_allowed": False}
    )
    if validation_payload:
        result["validation_status"] = validation_payload.get("status")
        result["normalized_fields"] = validation_payload.get("fields")
    else:
        result["validation_status"] = "pending_review"
        result["normalized_fields"] = {}

    try:
        from ocr.templates_registry import get_template

        if user_template is None and doc_type and doc_type != "unknown":
            template = get_template(doc_type)
            result["template"] = {
                "id": template.doc_type,
                "version": str(template.template_version),
                "title": template.title,
            }
    except Exception:
        pass

    result["status"] = "structured"
    return result


def process_job(job_id: str) -> dict[str, Any]:
    """Celery worker entry: OCR + structure + validate + store JSON."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist as exc:
        raise OcrPipelineError(f"Unknown job_id: {job_id}") from exc

    job.status = OcrJob.STATUS_OCR_PROCESSING
    job.error_message = ""
    job.save(update_fields=["status", "error_message", "updated_at"])

    store = get_object_store()
    try:
        content = store.get_bytes(job.original_object_key)
        result = recognize_document(
            content,
            filename=job.filename,
            content_type=job.content_type,
            document_id=job.document_id,
            job_id=job.job_id,
            sha256=job.sha256,
        )
        user_template = None
        if job.user_template_id:
            from ocr.models import OcrUserTemplate

            user_template = OcrUserTemplate.objects.filter(pk=job.user_template_id).first()
        result = _attach_structuring(
            result,
            filename=job.filename,
            document_type_hint="" if user_template is not None else job.document_type,
            user_template=user_template,
        )
        payload = json.dumps(result, ensure_ascii=False, indent=2).encode(
            "utf-8"
        )
        store.put_bytes(
            job.result_object_key,
            payload,
            content_type="application/json",
        )
    except (OcrEngineError, ObjectStoreError, OcrPipelineError) as exc:
        job.status = OcrJob.STATUS_ERROR
        job.error_message = str(exc)[:2000]
        job.save(
            update_fields=["status", "error_message", "updated_at"]
        )
        raise

    job.status = OcrJob.STATUS_COMPLETED
    job.completed_at = timezone.now()
    job.ocr_model = result["ocr_engine"]["version"]
    if job.user_template_id:
        job.document_type = ""
    else:
        job.document_type = str(result.get("document_type") or "")[:64]
    job.validation_status = str(result.get("validation_status") or "")[:32]
    job.save(
        update_fields=[
            "status",
            "completed_at",
            "ocr_model",
            "document_type",
            "validation_status",
            "updated_at",
        ]
    )
    return {
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": job.status,
        "document_type": job.document_type,
        "validation_status": job.validation_status,
        "result_object_key": job.result_object_key,
        "pages": len(result["pages"]),
        "field_count": result.get("field_count", 0),
    }


_JOB_PROGRESS = {
    OcrJob.STATUS_QUEUED: 0,
    OcrJob.STATUS_OCR_PROCESSING: 50,
    OcrJob.STATUS_COMPLETED: 100,
    OcrJob.STATUS_ERROR: 0,
}


def job_progress(status: str) -> int:
    return int(_JOB_PROGRESS.get(status, 0))


def job_to_dict(job: OcrJob) -> dict[str, Any]:
    error = job.error_message or None
    return {
        "job_id": job.job_id,
        "document_id": job.document_id,
        "status": job.status,
        "progress": job_progress(job.status),
        "filename": job.filename,
        "content_type": job.content_type,
        "sha256": job.sha256,
        "ocr_model": job.ocr_model,
        "document_type": job.document_type or None,
        "validation_status": job.validation_status or None,
        "original_object_key": job.original_object_key,
        "result_object_key": job.result_object_key or None,
        "error": error,
        "error_message": error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": (
            job.completed_at.isoformat() if job.completed_at else None
        ),
        "batch_id": job.batch_id or None,
        "source_archive": job.source_archive or None,
        "user_template_id": job.user_template_id,
        "pipeline": "IV.5+IV.8",
        "fr": ["FR-OCR-04", "FR-OCR-06", "FR-OCR-08", "FR-OCR-13", "FR-OCR-14"],
    }


def load_result(job: OcrJob) -> dict[str, Any]:
    if job.status != OcrJob.STATUS_COMPLETED:
        raise OcrPipelineError(
            f"Result not ready; status={job.status}"
        )
    if not job.result_object_key:
        raise OcrPipelineError("Result object key missing")
    store = get_object_store()
    try:
        raw = store.get_bytes(job.result_object_key)
    except ObjectStoreError as exc:
        raise OcrPipelineError(str(exc)) from exc
    return json.loads(raw.decode("utf-8"))


def recognize_bytes_inline(
    content: bytes,
    *,
    filename: str,
    content_type: str = "",
    created_by: str = "",
    document_type_hint: str = "",
) -> dict[str, Any]:
    """Sync helper for assistant: create job, process, return full result."""
    from io import BytesIO

    job = create_job_from_upload(
        BytesIO(content),
        filename=filename,
        content_type=content_type,
        created_by=created_by,
        document_type_hint=document_type_hint,
        run_inline=True,
    )
    result = load_result(job)
    return {
        "job": job_to_dict(job),
        "result": result,
    }
