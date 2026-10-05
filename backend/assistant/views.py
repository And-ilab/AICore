"""HTTP API for AI Assistant chat and FR-RPT-ASS reports (III.7 / III.10)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    JsonResponse,
    StreamingHttpResponse,
)
from django.utils.encoding import iri_to_uri
from django.views.decorators.http import require_http_methods

from assistant.ass_reports import (
    AssReportsError,
    build_analytics,
    build_csv_export,
    build_xlsx_export,
    catalog,
    export_filename,
    parse_report_filters,
)
from assistant.content_intent import generate_from_prompt
from assistant.doc_templates import (
    draft_payload,
    file_response,
    get_template,
    list_templates,
    parse_field_values,
    validation_error,
)
from assistant.docgen import DocgenError
from assistant.rpa import RpaError, launch_scenario, list_scenarios
from assistant.sandbox import SandboxError, prepare_snippet
from assistant.sql_access import list_accesses
from assistant.translate import TranslateError, translate_text
from assistant.chat import (
    AssistantChatError,
    iter_chat_sse,
    parse_chat_request,
)
from hub.skill_store import (
    SkillNotAvailable,
    SkillNotFound,
    SkillStoreError,
    create_user_skill,
    delete_user_skill,
    get_owned_skill,
    list_catalog_for_user,
    resolve_visible_skill_instruction,
    serialize_skill,
    update_user_skill,
)
from assistant.media_asr import (
    CHAT_MEDIA_EXTENSIONS,
    MediaAsrError,
    transcribe_upload,
)
from assistant.local_llm import get_models_status, select_model
from assistant.openapi import build_openapi_document
from auth.decorators import require_permissions
from auth.roles import PERM_ASSISTANT_REPORTS, PERM_ASSISTANT_USE
from hub.assistant_admin import (
    AssistantAdminError,
    list_chat_knowledge_bases,
    resolve_assistant_original_path,
)
from hub.kb_admin import KnowledgeBaseError, extract_document_text
from hub.models import AssistantKnowledgeBaseDocument, KnowledgeBaseDocument
from ingest.models import AssistantProductionChunk, CCProductionChunk

CHAT_ATTACHMENT_EXTENSIONS = frozenset(
    {".pdf", ".doc", ".docx", ".txt", ".rtf", ".xlsx"}
)
CHAT_OCR_EXTENSIONS = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"}
)
CHAT_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
FIELD_LABELS_RU = {
    "full_name": "ФИО",
    "surname": "Фамилия",
    "given_name": "Имя",
    "patronymic": "Отчество",
    "document_number": "Номер документа",
    "series": "Серия",
    "number": "Номер",
    "birth_date": "Дата рождения",
    "expiry_date": "Срок действия",
    "issue_date": "Дата выдачи",
    "date": "Дата",
    "payer": "Плательщик",
    "beneficiary": "Получатель",
    "amount": "Сумма",
    "purpose": "Назначение",
    "currency": "Валюта",
}
_FIELD_ORDER = tuple(FIELD_LABELS_RU.keys())


def _validation_error(exc: AssistantChatError) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


def _reports_validation_error(exc: AssReportsError) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_knowledge_bases(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/kbs/ — chat catalog synced with settings «Базы знаний»."""
    return JsonResponse(
        {
            "items": list_chat_knowledge_bases(seed=False),
            "namespace": "chat",
            "includes": ["assistant_*", "cc_production", "suz-bitrix"],
        }
    )


@require_http_methods(["GET", "PUT"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_models(request: HttpRequest) -> JsonResponse:
    """GET/PUT /api/v1/assistant/models/ — chat model catalog and active model."""
    if request.method == "GET":
        return JsonResponse(get_models_status())
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Invalid JSON"]}},
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["Body must be a JSON object"]},
            },
            status=400,
        )
    model_id = body.get("model_id") or body.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"model_id": ["Required"]},
            },
            status=400,
        )
    try:
        return JsonResponse(select_model(model_id))
    except RuntimeError as exc:
        return JsonResponse(
            {"error": "switch_failed", "details": str(exc)},
            status=502,
        )
    except ValueError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"model_id": [str(exc)]},
            },
            status=400,
        )


def _format_ocr_chat_text(result: Mapping) -> str:
    doc_type = str(result.get("document_type") or "unknown")
    fields = result.get("fields") or {}
    lines = [f"Распознан документ: {doc_type}"]
    if isinstance(fields, Mapping):
        ordered_keys = [key for key in _FIELD_ORDER if key in fields]
        ordered_keys.extend(key for key in fields if key not in _FIELD_ORDER)
        for key in ordered_keys:
            payload = fields[key]
            label = FIELD_LABELS_RU.get(str(key), str(key))
            if isinstance(payload, Mapping) and "value" in payload:
                value = payload.get("value")
                conf = payload.get("confidence")
                if conf is not None:
                    pct = int(round(float(conf) * 100))
                    lines.append(f"— {label}: {value} ({pct}%)")
                else:
                    lines.append(f"— {label}: {value}")
            else:
                lines.append(f"— {label}: {payload}")
    status = result.get("validation_status") or (
        (result.get("validation") or {}).get("status")
        if isinstance(result.get("validation"), Mapping)
        else ""
    )
    if status:
        lines.append(f"Статус проверки: {status}")
    return "\n".join(lines)


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_attachment_extract(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/attachments/extract — text for chat attachments."""
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"file": ["file is required"]},
            },
            status=400,
        )
    filename = Path(getattr(uploaded, "name", "") or "file").name
    extension = Path(filename).suffix.lower()
    if extension in CHAT_MEDIA_EXTENSIONS:
        try:
            recognized = transcribe_upload(uploaded, filename)
        except MediaAsrError as exc:
            return JsonResponse(
                {
                    "error": "validation_error",
                    "details": {"file": [str(exc)]},
                },
                status=400,
            )
        return JsonResponse(
            {
                "name": filename,
                "type": extension.lstrip(".") or recognized["kind"],
                "content_type": "",
                "size_bytes": 0,
                "text": recognized["text"],
                "media": {
                    "kind": recognized["kind"],
                    "engine": recognized["engine"],
                    "compressed": bool(recognized.get("compressed")),
                },
            }
        )
    # Images / scan PDFs → OCR pipeline; office docs → text extract.
    if extension in CHAT_OCR_EXTENSIONS and extension not in {
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
    }:
        # Prefer OCR for image scans; PDF may be either path.
        want_ocr = extension != ".pdf" or str(
            request.POST.get("mode") or request.GET.get("mode") or "auto"
        ).lower() in {"ocr", "auto"}
        if want_ocr and extension != ".pdf":
            return assistant_attachment_ocr(request)

    if extension not in CHAT_ATTACHMENT_EXTENSIONS | CHAT_OCR_EXTENSIONS:
        allowed = ", ".join(
            sorted(
                CHAT_ATTACHMENT_EXTENSIONS
                | CHAT_OCR_EXTENSIONS
                | CHAT_MEDIA_EXTENSIONS
            )
        )
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {
                    "file": [f"unsupported type; allowed: {allowed}"],
                },
            },
            status=400,
        )
    data = uploaded.read()
    if len(data) > CHAT_ATTACHMENT_MAX_BYTES:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {
                    "file": [
                        f"file too large; max {CHAT_ATTACHMENT_MAX_BYTES} bytes"
                    ],
                },
            },
            status=400,
        )
    # PDF with scan intent or image-like content: OCR.
    if extension in CHAT_OCR_EXTENSIONS:
        mode = str(
            request.POST.get("mode") or request.GET.get("mode") or "auto"
        ).lower()
        if mode == "ocr" or extension != ".pdf":
            from ocr.pipeline import OcrPipelineError, recognize_bytes_inline

            try:
                recognized = recognize_bytes_inline(
                    data,
                    filename=filename,
                    content_type=getattr(uploaded, "content_type", "") or "",
                    created_by=getattr(request.user, "username", "") or "",
                    document_type_hint=str(
                        request.POST.get("document_type") or ""
                    ),
                )
            except OcrPipelineError as exc:
                return JsonResponse(
                    {
                        "error": "validation_error",
                        "details": {"file": [str(exc)]},
                    },
                    status=400,
                )
            result = recognized["result"]
            content_type = getattr(uploaded, "content_type", "") or ""
            return JsonResponse(
                {
                    "name": filename,
                    "type": extension.lstrip(".") or "ocr",
                    "content_type": content_type,
                    "size_bytes": len(data),
                    "text": _format_ocr_chat_text(result),
                    "ocr": {
                        "job_id": recognized["job"]["job_id"],
                        "document_id": recognized["job"]["document_id"],
                        "document_type": result.get("document_type"),
                        "fields": result.get("fields") or {},
                        "validation_status": result.get("validation_status"),
                        "pages": result.get("pages") or [],
                    },
                }
            )

    try:
        text = extract_document_text(filename, data)
    except KnowledgeBaseError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"file": [str(exc)]},
            },
            status=400,
        )
    content_type = getattr(uploaded, "content_type", "") or ""
    kind = extension.lstrip(".") or content_type
    return JsonResponse(
        {
            "name": filename,
            "type": kind,
            "content_type": content_type,
            "size_bytes": len(data),
            "text": text,
        }
    )


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_attachment_ocr(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/attachments/ocr — sync OCR + field extraction."""
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"file": ["file is required"]},
            },
            status=400,
        )
    filename = Path(getattr(uploaded, "name", "") or "file").name
    extension = Path(filename).suffix.lower()
    if extension not in CHAT_OCR_EXTENSIONS:
        allowed = ", ".join(sorted(CHAT_OCR_EXTENSIONS))
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {
                    "file": [f"unsupported type; allowed: {allowed}"],
                },
            },
            status=400,
        )
    data = uploaded.read()
    if len(data) > CHAT_ATTACHMENT_MAX_BYTES:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {
                    "file": [
                        f"file too large; max {CHAT_ATTACHMENT_MAX_BYTES} bytes"
                    ],
                },
            },
            status=400,
        )
    from ocr.pipeline import OcrPipelineError, recognize_bytes_inline

    try:
        recognized = recognize_bytes_inline(
            data,
            filename=filename,
            content_type=getattr(uploaded, "content_type", "") or "",
            created_by=getattr(request.user, "username", "") or "",
            document_type_hint=str(request.POST.get("document_type") or ""),
        )
    except OcrPipelineError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"file": [str(exc)]},
            },
            status=400,
        )
    result = recognized["result"]
    content_type = getattr(uploaded, "content_type", "") or ""
    return JsonResponse(
        {
            "name": filename,
            "type": extension.lstrip(".") or "ocr",
            "content_type": content_type,
            "size_bytes": len(data),
            "text": _format_ocr_chat_text(result),
            "ocr": {
                "job_id": recognized["job"]["job_id"],
                "document_id": recognized["job"]["document_id"],
                "document_type": result.get("document_type"),
                "fields": result.get("fields") or {},
                "validation_status": result.get("validation_status"),
                "pages": result.get("pages") or [],
            },
        }
    )


def _download_filename(name: str, *, suffix: str = "") -> str:
    stem = Path(str(name or "document")).name.strip() or "document"
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", stem).strip(" .") or "document"
    if suffix and Path(cleaned).suffix.lower() != suffix.lower():
        return f"{Path(cleaned).stem}{suffix}"
    return cleaned


def _attachment_file_response(
    path: Path,
    *,
    filename: str,
    content_type: str,
) -> FileResponse:
    response = FileResponse(
        path.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type or "application/octet-stream",
    )
    response["X-Source-Filename"] = iri_to_uri(filename)
    return response


_URL_IN_TEXT = re.compile(r"(https?://[^\s]+)")
_SENTENCE_BREAK = re.compile(r"([.!?…])(\s+)(?=[«\"A-ZА-ЯЁ0-9])")


def _join_overlapping_chunks(parts: list[str]) -> str:
    pieces = [part.strip() for part in parts if part and part.strip()]
    if not pieces:
        return ""
    merged = pieces[0]
    for part in pieces[1:]:
        overlap = 0
        limit = min(len(merged), len(part), 480)
        for size in range(limit, 24, -1):
            if merged.endswith(part[:size]):
                overlap = size
                break
        merged = merged + part[overlap:] if overlap else f"{merged}\n\n{part}"
    return merged


def _readable_source_text(text: str) -> str:
    """Restore paragraphs lost when ingest collapsed whitespace."""
    cleaned = re.sub(r"[ \t]+", " ", (text or "").replace("\r\n", "\n")).strip()
    if not cleaned:
        return ""
    newline_count = cleaned.count("\n")
    if newline_count >= 4:
        return re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = _URL_IN_TEXT.sub(r"\n\1\n", cleaned)
    cleaned = _SENTENCE_BREAK.sub(r"\1\n\n", cleaned)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _attachment_text_response(*, title: str, text: str, filename: str) -> HttpResponse:
    download_name = _download_filename(filename or title, suffix=".txt")
    header = (title or Path(download_name).stem).strip()
    readable = _readable_source_text(text)
    body = readable if readable.startswith(header) else f"{header}\n\n{readable}"
    response = HttpResponse(
        body.encode("utf-8"),
        content_type="text/plain; charset=utf-8",
    )
    ascii_name = download_name if download_name.isascii() else "document.txt"
    response["Content-Disposition"] = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(download_name)}"
    )
    response["X-Source-Filename"] = quote(download_name, safe="._-")
    response["X-Source-Fallback"] = "extracted_text"
    return response


def _joined_chunk_text(queryset) -> tuple[str, str]:
    rows = list(queryset.order_by("chunk_index").values("title", "content"))
    if not rows:
        return "", ""
    title = str(rows[0].get("title") or "Источник")
    text = _join_overlapping_chunks(
        [str(row.get("content") or "") for row in rows]
    )
    return title, text


def _resolve_cited_source(kb_slug: str, article_id: int) -> HttpResponse | None:
    assistant_docs = AssistantKnowledgeBaseDocument.objects.select_related(
        "knowledge_base"
    )
    document = assistant_docs.filter(
        article_id=article_id, knowledge_base__slug=kb_slug
    ).first()
    if document is None:
        document = assistant_docs.filter(article_id=article_id).first()
    if document is not None:
        filename = Path(document.filename).name or "document.bin"
        original = resolve_assistant_original_path(document)
        if original is not None:
            return _attachment_file_response(
                original,
                filename=filename,
                content_type=document.content_type or "application/octet-stream",
            )
        text = (document.extracted_text or "").strip()
        if text:
            return _attachment_text_response(
                title=Path(filename).stem, text=text, filename=filename
            )

    cc_docs = KnowledgeBaseDocument.objects.select_related("knowledge_base")
    cc_document = cc_docs.filter(
        article_id=article_id, knowledge_base__slug=kb_slug
    ).first()
    if cc_document is None:
        cc_document = cc_docs.filter(article_id=article_id).first()
    if cc_document is not None:
        filename = Path(cc_document.filename).name or "document.bin"
        text = (cc_document.extracted_text or "").strip()
        if text:
            return _attachment_text_response(
                title=Path(filename).stem, text=text, filename=filename
            )

    title, text = _joined_chunk_text(
        AssistantProductionChunk.objects.filter(
            is_active=True, article_id=article_id, kb_slug=kb_slug
        )
    )
    if not text:
        title, text = _joined_chunk_text(
            AssistantProductionChunk.objects.filter(
                is_active=True, article_id=article_id
            )
        )
    if not text:
        title, text = _joined_chunk_text(
            CCProductionChunk.objects.filter(is_active=True, article_id=article_id)
        )
    if text:
        safe_name = Path(title).name or f"article-{article_id}"
        return _attachment_text_response(
            title=title, text=text, filename=f"{safe_name}.txt"
        )
    return None


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_source_download(request: HttpRequest) -> HttpResponse:
    """GET /api/v1/assistant/sources/download — open cited KB file from chat."""
    kb_slug = str(request.GET.get("kb_slug") or "").strip()
    article_raw = str(request.GET.get("article_id") or "").strip()
    if not kb_slug or not article_raw:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {
                    "request": ["kb_slug and article_id are required"],
                },
            },
            status=400,
        )
    try:
        article_id = int(article_raw)
    except ValueError:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"article_id": ["must be an integer"]},
            },
            status=400,
        )
    response = _resolve_cited_source(kb_slug, article_id)
    if response is not None:
        return response
    return JsonResponse(
        {
            "error": "not_found",
            "details": {
                "file": ["Не удалось открыть файл источника."],
            },
        },
        status=404,
    )


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_chat(request: HttpRequest) -> StreamingHttpResponse | JsonResponse:
    """POST /api/v1/assistant/chat — SSE stream via ModelGateway assistant_bank."""
    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, Mapping):
            raise AssistantChatError("Request body must be a JSON object")
        parsed = parse_chat_request(body)
        skill_instruction = ""
        if parsed.get("skill_id") is not None:
            skill_instruction = resolve_visible_skill_instruction(
                parsed["skill_id"],
                request.user,
            )
    except json.JSONDecodeError:
        return _validation_error(
            AssistantChatError("Request body must be valid JSON")
        )
    except SkillNotAvailable as exc:
        return _validation_error(AssistantChatError(str(exc)))
    except AssistantChatError as exc:
        return _validation_error(exc)

    request_id = getattr(request, "audit_request_id", None) or parsed[
        "session_id"
    ]

    def event_stream():
        yield from iter_chat_sse(
            parsed["messages"],
            kb_slugs=parsed.get("kb_slugs") or [],
            request_id=str(request_id),
            expand=bool(parsed.get("expand")),
            skill_instruction=skill_instruction,
        )

    response = StreamingHttpResponse(
        event_stream(),
        content_type="text/event-stream; charset=utf-8",
    )
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    response["X-Request-ID"] = str(request_id)
    response["X-Assistant-Profile"] = "assistant_bank"
    response["X-Session-ID"] = parsed["session_id"]
    return response


@require_http_methods(["GET"])
def assistant_openapi(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/openapi.json — generated OpenAPI 3 schema."""
    return JsonResponse(build_openapi_document())


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_REPORTS, api=True)
def assistant_reports_catalog(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/reports/ — FR-RPT-ASS catalog (III.10.2)."""
    return JsonResponse(catalog())


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_REPORTS, api=True)
def assistant_reports_analytics(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/reports/analytics/ — usage, feedback, tools."""
    try:
        filters = parse_report_filters(request.GET)
        return JsonResponse(build_analytics(filters))
    except AssReportsError as exc:
        return _reports_validation_error(exc)


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_REPORTS, api=True)
def assistant_report_detail(request: HttpRequest, report_id: str) -> JsonResponse:
    """GET /api/v1/assistant/reports/<FR-RPT-ASS-XX>/ — single FR section."""
    try:
        filters = parse_report_filters(request.GET)
        filters["report_id"] = report_id
        if report_id not in {
            item["id"] for item in catalog()["items"]
        }:
            raise AssReportsError(f"Unknown report_id: {report_id}")
        payload = build_analytics(filters)
        payload["report_id"] = report_id
        return JsonResponse(payload)
    except AssReportsError as exc:
        return _reports_validation_error(exc)


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_REPORTS, api=True)
def assistant_reports_export(request: HttpRequest) -> HttpResponse:
    """GET /api/v1/assistant/reports/export/ — CSV/XLSX (FR-RPT-ASS-07)."""
    try:
        filters = parse_report_filters(request.GET)
        analytics = build_analytics(filters)
        export_format = filters["format"]
        if export_format == "xlsx":
            payload = build_xlsx_export(analytics)
            content_type = (
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            )
        else:
            payload = build_csv_export(analytics)
            content_type = "text/csv; charset=utf-8"
        filename = export_filename(filters, export_format)
    except AssReportsError as exc:
        return _reports_validation_error(exc)

    response = HttpResponse(payload, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["X-FR-Catalog"] = "FR-RPT-ASS"
    return response


def _kb_slugs(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    slugs = [str(item).strip() for item in raw if str(item).strip()]
    return slugs or None


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_doc_templates(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/doc-templates/ — active bank blanks for UC-ASS-05."""
    return JsonResponse({"items": list_templates(active_only=True)})


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_doc_template_generate(
    request: HttpRequest,
    template_id: int,
) -> HttpResponse:
    """POST /api/v1/assistant/doc-templates/<id>/generate/ — draft JSON or file."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["Invalid JSON"]},
            },
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["Body must be a JSON object"]},
            },
            status=400,
        )
    mode = str(body.get("mode") or "download").strip().lower()
    if mode not in {"draft", "download"}:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"mode": ["must be draft or download"]},
            },
            status=400,
        )
    try:
        template = get_template(template_id)
        if not template.active:
            raise AssistantAdminError("template not found")
        values = parse_field_values(body.get("fields"))
        prompt = str(body.get("prompt") or "").strip()
        kb_slugs = _kb_slugs(body.get("kb_slugs"))
        if mode == "draft":
            return JsonResponse(
                draft_payload(template, values, prompt=prompt, kb_slugs=kb_slugs)
            )
        return file_response(template, values, prompt=prompt, kb_slugs=kb_slugs)
    except AssistantAdminError as exc:
        if str(exc) == "template not found":
            return JsonResponse({"error": "not_found"}, status=404)
        return validation_error(exc)
    except DocgenError as exc:
        return validation_error(exc)


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_content_from_prompt(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/content/from-prompt/ — UC-ASS-06/07 from chat text."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["Invalid JSON"]},
            },
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["Body must be a JSON object"]},
            },
            status=400,
        )
    message = str(body.get("message") or "").strip()
    if not message:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"message": ["Required"]},
            },
            status=400,
        )
    try:
        return JsonResponse(generate_from_prompt(message))
    except AssistantAdminError as exc:
        return validation_error(exc)
    except DocgenError as exc:
        return validation_error(exc)


def _skill_validation_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )


def _parse_skill_body(request: HttpRequest) -> Mapping[str, Any]:
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise SkillStoreError("Request body must be valid JSON") from exc
    if not isinstance(body, Mapping):
        raise SkillStoreError("Request body must be a JSON object")
    return body


@require_http_methods(["GET", "POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_skills(request: HttpRequest) -> JsonResponse:
    """GET catalog (Банк + Мои) / POST personal skill."""
    if request.method == "GET":
        return JsonResponse({"items": list_catalog_for_user(request.user)})
    try:
        created = create_user_skill(
            _parse_skill_body(request),
            user=request.user,
        )
    except SkillStoreError as exc:
        return _skill_validation_error(exc)
    return JsonResponse(created, status=201)


@require_http_methods(["GET", "PUT", "PATCH", "DELETE"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_skill_detail(
    request: HttpRequest,
    skill_id: int,
) -> JsonResponse:
    try:
        if request.method == "GET":
            return JsonResponse(serialize_skill(get_owned_skill(skill_id, request.user)))
        if request.method == "DELETE":
            delete_user_skill(skill_id, request.user)
            return JsonResponse({"ok": True})
        updated = update_user_skill(
            skill_id,
            _parse_skill_body(request),
            user=request.user,
        )
    except SkillNotFound:
        return JsonResponse({"error": "not_found"}, status=404)
    except SkillStoreError as exc:
        return _skill_validation_error(exc)
    return JsonResponse(updated)


def _rpa_error(exc: RpaError, *, status: int = 400) -> JsonResponse:
    if str(exc) == "scenario not found":
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {"error": "validation_error", "details": {"request": [str(exc)]}},
        status=status,
    )


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_rpa_scenarios(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/rpa/scenarios/ — whitelist for the chat picker."""
    return JsonResponse({"items": list_scenarios(active_only=True)})


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_rpa_launch(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/rpa/launch/ — confirm a whitelisted scenario."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Invalid JSON"]}},
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Body must be a JSON object"]}},
            status=400,
        )
    try:
        scenario_id = int(body.get("scenario_id"))
    except (TypeError, ValueError):
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Укажите сценарий"]}},
            status=400,
        )
    try:
        payload = launch_scenario(
            scenario_id,
            username=request.user.get_username(),
            confirm=bool(body.get("confirm")),
        )
    except RpaError as exc:
        status = 403 if str(exc) == "Сценарий не в белом списке" else 400
        return _rpa_error(exc, status=status)
    return JsonResponse(payload, status=201)


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_sandbox_snippet(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/sandbox/ — show SQL or code. No database is queried."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Invalid JSON"]}},
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Body must be a JSON object"]}},
            status=400,
        )
    try:
        payload = prepare_snippet(
            str(body.get("kind") or ""),
            str(body.get("text") or ""),
            request=request,
        )
    except SandboxError as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(payload)


@require_http_methods(["GET"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_sql_access(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/assistant/sql/access/ — vitrines the operator may name. Not queried."""
    return JsonResponse({"items": list_accesses(active_only=True)})


@require_http_methods(["POST"])
@require_permissions(PERM_ASSISTANT_USE, api=True)
def assistant_translate(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/assistant/translate/ — RU↔EN text. Files are not accepted."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Invalid JSON"]}},
            status=400,
        )
    if not isinstance(body, Mapping):
        return JsonResponse(
            {"error": "validation_error", "details": {"request": ["Body must be a JSON object"]}},
            status=400,
        )
    try:
        payload = translate_text(
            str(body.get("text") or ""),
            str(body.get("direction") or ""),
        )
    except TranslateError as exc:
        return JsonResponse(
            {"error": "validation_error", "details": {"request": [str(exc)]}},
            status=400,
        )
    return JsonResponse(payload)
