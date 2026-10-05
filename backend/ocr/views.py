"""HTTP API for OCR upload, templates, validation, and export (IV.5 / IV.8)."""

from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from typing import Any, Mapping

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from auth.decorators import require_permissions
from auth.roles import PERM_OCR_ADMIN, PERM_OCR_USE
from ocr.export import build_export, export_filename, normalize_export_format
from ocr.models import OcrJob
from ocr.storage import ObjectStoreError, get_object_store
from ocr.pipeline import (
    OcrPipelineError,
    create_jobs_from_upload,
    job_to_dict,
    load_result,
    recognize_bytes_inline,
)
from ocr.user_templates import (
    UserTemplateError,
    UserTemplateNameTaken,
    UserTemplateNotFound,
    create_from_job,
    delete_template,
    get_owned,
    list_for_user,
    serialize_user_template,
    update_template,
)
from ocr.templates_registry import (
    TemplateRegistryError,
    add_template_sample,
    get_template,
    list_templates,
    seed_templates_from_yaml,
    template_to_dict,
    upsert_template,
)
from ocr.validation import (
    ValidationRequestError,
    list_document_types,
    validate_document,
)


def _validation_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


def _parse_json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationRequestError("Request body must be valid JSON") from exc
    if not isinstance(body, Mapping):
        raise ValidationRequestError("Request body must be a JSON object")
    return dict(body)


def _actor(request: HttpRequest) -> str:
    return getattr(request.user, "username", "") or ""


def _document_type_hint(request: HttpRequest) -> str:
    return str(
        request.POST.get("doc_type")
        or request.POST.get("document_type")
        or request.GET.get("doc_type")
        or request.GET.get("document_type")
        or ""
    ).strip()


def _ocr_mode(request: HttpRequest) -> str:
    raw = str(request.POST.get("mode") or request.GET.get("mode") or "").strip().lower()
    if raw in {"template", "ml"}:
        return raw
    return ""


def _user_template_from_request(request: HttpRequest):
    raw = str(
        request.POST.get("user_template_id") or request.GET.get("user_template_id") or ""
    ).strip()
    if not raw:
        return None
    try:
        template_id = int(raw)
    except (TypeError, ValueError) as exc:
        raise OcrPipelineError("user_template_id must be an integer") from exc
    return get_owned(template_id, request.user)


def _template_error(exc: Exception) -> JsonResponse:
    if isinstance(exc, UserTemplateNotFound):
        return JsonResponse({"error": "not_found", "details": {"request": [str(exc)]}}, status=404)
    return _validation_error(exc)


def _enqueue_upload(request: HttpRequest, *, allow_sync: bool) -> JsonResponse:
    upload = request.FILES.get("file") or request.FILES.get("document")
    if upload is None:
        return _validation_error(
            OcrPipelineError("multipart field 'file' (or 'document') is required")
        )
    mode = _ocr_mode(request)
    document_type_hint = _document_type_hint(request)
    try:
        user_template = _user_template_from_request(request)
    except (UserTemplateNotFound, OcrPipelineError) as exc:
        if isinstance(exc, UserTemplateNotFound):
            return _template_error(exc)
        return _validation_error(exc)
    if mode == "template" and not document_type_hint and user_template is None:
        return _validation_error(
            OcrPipelineError("mode=template требует doc_type или document_type")
        )
    if user_template is not None:
        document_type_hint = ""
    try:
        run_inline = allow_sync and str(
            request.POST.get("sync") or request.GET.get("sync") or ""
        ).lower() in {"1", "true", "yes"}
        bundle = create_jobs_from_upload(
            upload,
            filename=getattr(upload, "name", "") or "upload.bin",
            content_type=getattr(upload, "content_type", "") or "",
            created_by=_actor(request),
            document_type_hint=document_type_hint,
            run_inline=run_inline,
            user_template_id=user_template.id if user_template else None,
        )
    except OcrPipelineError as exc:
        return _validation_error(exc)

    jobs = bundle["jobs"]
    job = jobs[0]
    payload = job_to_dict(job)
    payload["items"] = [job_to_dict(item) for item in jobs]
    payload["batch_id"] = bundle.get("batch_id") or payload.get("batch_id")
    payload["archive"] = bundle.get("archive") or None
    payload["skipped"] = bundle.get("skipped") or []
    if mode:
        payload["mode"] = mode
    if len(jobs) > 1:
        payload["message"] = "OCR jobs completed" if run_inline else "OCR jobs queued"
    else:
        payload["message"] = "OCR job completed" if run_inline else "OCR job queued"
    if run_inline and job.status == OcrJob.STATUS_COMPLETED:
        try:
            payload["result"] = load_result(job)
        except OcrPipelineError:
            pass
    return JsonResponse(payload, status=202 if not run_inline else 200)


@csrf_exempt
@require_http_methods(["POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_upload(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/ocr/documents/ — alias of POST /jobs/ (keeps sync for admin UI)."""
    return _enqueue_upload(request, allow_sync=True)


@csrf_exempt
@require_http_methods(["GET", "POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_jobs_list(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/ocr/jobs/ — list. POST — multipart enqueue (P6-01a)."""
    if request.method == "POST":
        return _enqueue_upload(request, allow_sync=False)
    limit = min(int(request.GET.get("limit") or 50), 200)
    jobs = OcrJob.objects.all()[:limit]
    return JsonResponse({"items": [job_to_dict(job) for job in jobs]})


@require_http_methods(["GET"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_job_detail(request: HttpRequest, job_id: str) -> JsonResponse:
    """GET /api/v1/ocr/jobs/<job_id>/ — job status metadata."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)
    return JsonResponse(job_to_dict(job))


@require_http_methods(["GET"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_job_result(request: HttpRequest, job_id: str) -> JsonResponse:
    """GET /api/v1/ocr/jobs/<job_id>/result/ — OCR JSON from object storage."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)

    if job.status == OcrJob.STATUS_ERROR:
        return JsonResponse(
            {
                "error": "processing_error",
                "job_id": job.job_id,
                "message": job.error_message,
            },
            status=422,
        )
    if job.status != OcrJob.STATUS_COMPLETED:
        return JsonResponse(
            {
                "error": "not_ready",
                "job_id": job.job_id,
                "status": job.status,
            },
            status=409,
        )

    try:
        result = load_result(job)
    except OcrPipelineError as exc:
        return _validation_error(exc)
    return JsonResponse(result)


@require_http_methods(["GET"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_job_original(request: HttpRequest, job_id: str) -> HttpResponse:
    """GET /api/v1/ocr/jobs/<job_id>/original/ — original scan for HITL preview."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)
    if not job.original_object_key:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)
    try:
        payload = get_object_store().get_bytes(job.original_object_key)
    except ObjectStoreError:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)
    guessed, _ = mimetypes.guess_type(job.filename or "")
    content_type = job.content_type or guessed or "application/octet-stream"
    safe_name = Path(job.filename or "document").name.replace('"', "")
    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{safe_name}"'
    response["Cache-Control"] = "private, max-age=120"
    return response


@csrf_exempt
@require_http_methods(["POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_job_approve(request: HttpRequest, job_id: str) -> JsonResponse:
    """POST /api/v1/ocr/jobs/<id>/approve/ — HITL confirm/edit fields (FR-OCR-15/24)."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)
    try:
        body = _parse_json_body(request)
        fields = body.get("fields")
        if not isinstance(fields, Mapping):
            raise ValidationRequestError("fields must be an object")
        if job.user_template_id:
            stored = load_result(job) if job.status == OcrJob.STATUS_COMPLETED else {}
            stored["fields"] = dict(fields)
            stored["normalized_fields"] = dict(fields)
            stored["validation"] = {
                "status": "approved",
                "downstream_allowed": True,
            }
            stored["validation_status"] = "approved"
            stored["approved_by"] = _actor(request)
            stored["hitl"] = {"approved": True, "actor": _actor(request)}
            stored["user_template_id"] = job.user_template_id
            from ocr.storage import get_object_store

            store = get_object_store()
            store.put_bytes(
                job.result_object_key,
                json.dumps(stored, ensure_ascii=False, indent=2).encode("utf-8"),
                content_type="application/json",
            )
            job.validation_status = "approved"
            job.save(update_fields=["validation_status", "updated_at"])
            return JsonResponse(
                {
                    "job": job_to_dict(job),
                    "validation": {"status": "approved", "fields": dict(fields)},
                }
            )
        document_type = str(
            body.get("document_type") or job.document_type or ""
        ).strip()
        if not document_type:
            raise ValidationRequestError("document_type is required")
        result = validate_document(
            document_type,
            fields,
            job_id=job.job_id,
            document_id=job.document_id,
            document_sha256=job.sha256,
        )
        stored = load_result(job) if job.status == OcrJob.STATUS_COMPLETED else {}
        stored["fields"] = dict(fields)
        stored["normalized_fields"] = result.normalized_fields
        stored["validation"] = result.as_dict().get("validation")
        stored["validation_status"] = result.status
        stored["document_type"] = document_type
        stored["approved_by"] = _actor(request)
        stored["hitl"] = {"approved": result.is_valid, "actor": _actor(request)}
        from ocr.storage import get_object_store

        store = get_object_store()
        store.put_bytes(
            job.result_object_key,
            json.dumps(stored, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )
        job.document_type = document_type[:64]
        job.validation_status = result.status[:32]
        job.save(
            update_fields=["document_type", "validation_status", "updated_at"]
        )
    except (ValidationRequestError, OcrPipelineError) as exc:
        return _validation_error(exc)

    status_code = 200 if result.is_valid else 422
    return JsonResponse(
        {
            "job": job_to_dict(job),
            "validation": result.as_dict(),
        },
        status=status_code,
    )


@require_http_methods(["GET"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_doc_types(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/ocr/doc-types/ — configurable validation templates."""
    db_items = list_templates(include_drafts=False)
    if db_items:
        items = [
            {
                "doc_type": item["doc_type"],
                "title": item["title"],
                "template_version": str(item["template_version"]),
                "required_fields": item["required_fields"],
                "field_schema": item.get("field_schema") or {},
                "confidence_min": item["confidence_min"],
                "status": item["status"],
            }
            for item in db_items
        ]
    else:
        items = list_document_types()
    return JsonResponse(
        {
            "section": "IV.8",
            "acceptance": ["DOC-T-04", "FR-OCR-14"],
            "items": items,
        }
    )


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_OCR_ADMIN, api=True)
def ocr_templates(request: HttpRequest) -> JsonResponse:
    """GET/POST /api/v1/ocr/templates/ — admin template registry."""
    if request.method == "GET":
        if request.GET.get("seed") == "1":
            seed_templates_from_yaml()
        return JsonResponse({"items": list_templates(include_drafts=True)})
    try:
        body = _parse_json_body(request)
        item = upsert_template(body, actor=_actor(request))
    except (TemplateRegistryError, ValidationRequestError) as exc:
        return _validation_error(exc)
    return JsonResponse(item, status=201)


@require_http_methods(["GET", "PUT"])
@require_permissions(PERM_OCR_ADMIN, api=True)
def ocr_template_detail(request: HttpRequest, doc_type: str) -> JsonResponse:
    """GET/PUT /api/v1/ocr/templates/<doc_type>/."""
    try:
        if request.method == "GET":
            return JsonResponse(
                template_to_dict(get_template(doc_type), include_samples=True)
            )
        body = _parse_json_body(request)
        body["doc_type"] = doc_type
        return JsonResponse(upsert_template(body, actor=_actor(request)))
    except (TemplateRegistryError, ValidationRequestError) as exc:
        return _validation_error(exc)


@require_http_methods(["POST"])
@require_permissions(PERM_OCR_ADMIN, api=True)
def ocr_template_sample(request: HttpRequest, doc_type: str) -> JsonResponse:
    """POST /api/v1/ocr/templates/<doc_type>/samples/ — train with labeled sample."""
    upload = request.FILES.get("file")
    try:
        if upload is not None:
            raw = upload.read()
            filename = getattr(upload, "name", "") or "sample.bin"
            content_type = getattr(upload, "content_type", "") or ""
            # Prefer inline OCR for admin sample labeling.
            recognized = recognize_bytes_inline(
                raw,
                filename=filename,
                content_type=content_type,
                created_by=_actor(request),
                document_type_hint=doc_type,
            )
            ocr_text = "\n".join(
                str(page.get("text") or "")
                for page in (recognized["result"].get("pages") or [])
            )
            expected_raw = request.POST.get("expected_fields") or "{}"
            expected = json.loads(expected_raw) if expected_raw else {}
            if not isinstance(expected, Mapping):
                raise TemplateRegistryError("expected_fields must be a JSON object")
            if not expected:
                # Default expected fields from recognition for quick training.
                plain = {}
                for key, value in (recognized["result"].get("fields") or {}).items():
                    if isinstance(value, Mapping) and "value" in value:
                        plain[key] = value["value"]
                    else:
                        plain[key] = value
                expected = plain
            sample = add_template_sample(
                doc_type,
                filename=filename,
                ocr_text=ocr_text,
                expected_fields=expected,
                content_type=content_type,
                notes=request.POST.get("notes") or "",
                actor=_actor(request),
                object_key=recognized["job"].get("original_object_key") or "",
            )
            sample["recognition"] = {
                "job_id": recognized["job"]["job_id"],
                "fields": recognized["result"].get("fields") or {},
                "document_type": recognized["result"].get("document_type"),
            }
            return JsonResponse(sample, status=201)

        body = _parse_json_body(request)
        sample = add_template_sample(
            doc_type,
            filename=str(body.get("filename") or "manual.txt"),
            ocr_text=str(body.get("ocr_text") or ""),
            expected_fields=body.get("expected_fields") or {},
            notes=str(body.get("notes") or ""),
            actor=_actor(request),
        )
        return JsonResponse(sample, status=201)
    except (
        TemplateRegistryError,
        ValidationRequestError,
        OcrPipelineError,
        json.JSONDecodeError,
    ) as exc:
        return _validation_error(exc)


@require_http_methods(["POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_validate(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/ocr/validate/ — run rules for a doc_type (DOC-T-04)."""
    try:
        body = _parse_json_body(request)
        document_type = str(body.get("document_type") or "").strip()
        fields = body.get("fields")
        if not isinstance(fields, Mapping):
            raise ValidationRequestError("fields must be an object")
        result = validate_document(
            document_type,
            fields,
            job_id=body.get("job_id"),
            document_id=body.get("document_id"),
            document_sha256=body.get("document_sha256"),
        )
    except (ValidationRequestError, OcrPipelineError) as exc:
        return _validation_error(exc)

    status_code = 200 if result.is_valid else 422
    return JsonResponse(result.as_dict(), status=status_code)


@require_http_methods(["POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_export(request: HttpRequest) -> HttpResponse:
    """POST /api/v1/ocr/export/?format=json|csv|pdf|docx — validated downstream payload."""
    try:
        body = _parse_json_body(request)
        export_format = normalize_export_format(
            request.GET.get("format") or body.get("format")
        )
        document_type = str(body.get("document_type") or "").strip()
        fields = body.get("fields")
        if not isinstance(fields, Mapping):
            raise ValidationRequestError("fields must be an object")
        result = validate_document(
            document_type,
            fields,
            job_id=body.get("job_id"),
            document_id=body.get("document_id"),
            document_sha256=body.get("document_sha256"),
        )
        require_valid = body.get("require_valid", True)
        if not isinstance(require_valid, bool):
            require_valid = True
        payload, content_type = build_export(
            result,
            export_format,
            require_valid=require_valid,
        )
        filename = export_filename(result, export_format)
    except ValidationRequestError as exc:
        return _validation_error(exc)

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-OCR-Status"] = result.status
    response["X-DOC-T"] = "DOC-T-08"
    return response


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_job_export(request: HttpRequest, job_id: str) -> HttpResponse:
    """GET|POST /api/v1/ocr/jobs/<id>/export/ — validate job fields and export."""
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist:
        return JsonResponse({"error": "not_found", "job_id": job_id}, status=404)

    try:
        if request.method == "POST":
            body = _parse_json_body(request)
        else:
            body = {}
        export_format = normalize_export_format(
            request.GET.get("format") or body.get("format")
        )
        document_type = str(
            body.get("document_type")
            or request.GET.get("document_type")
            or job.document_type
            or ""
        ).strip()
        fields = body.get("fields")
        if not isinstance(fields, Mapping):
            if job.status == OcrJob.STATUS_COMPLETED:
                stored = load_result(job)
                fields = stored.get("fields") or stored.get("normalized_fields")
            if not isinstance(fields, Mapping):
                raise ValidationRequestError(
                    "fields object is required (POST JSON or completed job result)"
                )
        if not document_type:
            raise ValidationRequestError("document_type is required")
        result = validate_document(
            document_type,
            fields,
            job_id=job.job_id,
            document_id=job.document_id,
            document_sha256=job.sha256,
        )
        require_valid = body.get("require_valid", True)
        if not isinstance(require_valid, bool):
            require_valid = True
        payload, content_type = build_export(
            result,
            export_format,
            require_valid=require_valid,
        )
        filename = export_filename(result, export_format)
    except (ValidationRequestError, OcrPipelineError) as exc:
        return _validation_error(exc)

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-OCR-Status"] = result.status
    response["X-DOC-T"] = "DOC-T-08"
    return response


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_my_templates(request: HttpRequest) -> JsonResponse:
    """GET/POST /api/v1/ocr/my-templates/ — personal templates (P6-03a)."""
    if request.method == "GET":
        return JsonResponse({"items": list_for_user(request.user)})
    try:
        body = _parse_json_body(request)
        job_id = str(body.get("job_id") or "").strip()
        if not job_id:
            raise UserTemplateError("job_id is required")
        created = create_from_job(
            request.user,
            job_id=job_id,
            name=str(body.get("name") or ""),
        )
    except UserTemplateNotFound as exc:
        return _template_error(exc)
    except (UserTemplateNameTaken, UserTemplateError, ValidationRequestError) as exc:
        return _template_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
@require_permissions(PERM_OCR_USE, api=True)
def ocr_my_template_detail(request: HttpRequest, template_id: int) -> JsonResponse:
    """GET/PATCH/DELETE /api/v1/ocr/my-templates/<id>/ — owner only."""
    try:
        if request.method == "GET":
            return JsonResponse(serialize_user_template(get_owned(template_id, request.user)))
        if request.method == "DELETE":
            delete_template(template_id, request.user)
            return JsonResponse({"ok": True})
        body = _parse_json_body(request)
        if "name" not in body and "fields" not in body:
            raise UserTemplateError("укажите name или fields")
        updated = update_template(
            template_id,
            request.user,
            name=None if "name" not in body else str(body.get("name") or ""),
            fields=body["fields"] if "fields" in body else None,
        )
    except UserTemplateNotFound as exc:
        return _template_error(exc)
    except (UserTemplateNameTaken, UserTemplateError, ValidationRequestError) as exc:
        return _template_error(exc)
    return JsonResponse(updated)
