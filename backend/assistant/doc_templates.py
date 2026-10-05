"""CRUD and generation for UC-ASS-05 document blanks."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from django.http import HttpResponse, JsonResponse

from assistant.docgen import DocgenError, build_document, render_body
from hub.assistant_admin import AssistantAdminError
from hub.models import AssistantDocumentTemplate

_FIELD_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
FORMAT_LABELS = dict(AssistantDocumentTemplate.FORMAT_CHOICES)
ALLOWED_FORMATS = {choice[0] for choice in AssistantDocumentTemplate.FORMAT_CHOICES}


def serialize_template(
    item: AssistantDocumentTemplate,
    *,
    include_body: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": item.pk,
        "name": item.name,
        "category": item.category,
        "output_format": item.output_format,
        "format_label": FORMAT_LABELS.get(item.output_format, item.output_format),
        "fields": list(item.fields or []),
        "active": item.active,
        "updated_by": item.updated_by,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }
    if include_body:
        payload["body"] = item.body
    return payload


def list_templates(*, active_only: bool = False) -> list[dict[str, Any]]:
    queryset = AssistantDocumentTemplate.objects.all()
    if active_only:
        queryset = queryset.filter(active=True)
    return [
        serialize_template(item, include_body=not active_only)
        for item in queryset
    ]


def get_template(template_id: int) -> AssistantDocumentTemplate:
    try:
        return AssistantDocumentTemplate.objects.get(pk=template_id)
    except AssistantDocumentTemplate.DoesNotExist as exc:
        raise AssistantAdminError("template not found") from exc


def _normalize_fields(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AssistantAdminError("fields must be a list")
    seen: set[str] = set()
    fields: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise AssistantAdminError("each field must be an object")
        field_id = str(item.get("id") or "").strip()
        if not _FIELD_ID_RE.match(field_id):
            raise AssistantAdminError(
                "field id: латинские буквы, цифры и _, начинается с буквы"
            )
        if field_id in seen:
            raise AssistantAdminError(f"дублируется поле {field_id}")
        seen.add(field_id)
        fields.append(
            {
                "id": field_id,
                "label": str(item.get("label") or field_id).strip()[:120],
                "required": bool(item.get("required")),
            }
        )
    return fields


def _apply_payload(
    item: AssistantDocumentTemplate,
    payload: Mapping[str, Any],
    *,
    username: str,
    creating: bool,
) -> None:
    if creating or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise AssistantAdminError("name is required")
        item.name = name[:200]
    if creating or "category" in payload:
        item.category = str(payload.get("category") or "Общее").strip()[:64] or "Общее"
    if creating or "output_format" in payload:
        fmt = str(payload.get("output_format") or AssistantDocumentTemplate.FORMAT_DOCX)
        if fmt not in ALLOWED_FORMATS:
            raise AssistantAdminError(
                "output_format must be docx|pdf|xlsx|pptx|bpmn"
            )
        item.output_format = fmt
    if creating or "body" in payload:
        body = str(payload.get("body") or "")
        if not body.strip():
            raise AssistantAdminError("body is required")
        item.body = body
    if creating or "fields" in payload:
        item.fields = _normalize_fields(payload.get("fields"))
    if "active" in payload:
        item.active = bool(payload.get("active"))
    elif creating:
        item.active = True
    item.updated_by = username


def create_template(payload: Mapping[str, Any], *, username: str) -> dict[str, Any]:
    item = AssistantDocumentTemplate()
    _apply_payload(item, payload, username=username, creating=True)
    item.save()
    return serialize_template(item)


def update_template(
    template_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    item = get_template(template_id)
    _apply_payload(item, payload, username=username, creating=False)
    item.save()
    return serialize_template(item)


def delete_template(template_id: int) -> None:
    get_template(template_id).delete()


def parse_field_values(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise DocgenError("fields must be an object")
    return {str(key): "" if value is None else str(value) for key, value in raw.items()}


def draft_payload(
    template: AssistantDocumentTemplate,
    values: Mapping[str, Any],
    *,
    strict: bool = True,
    prompt: str = "",
    kb_slugs: Sequence[str] | None = None,
) -> dict[str, Any]:
    from assistant.docgen import compose_document_text

    if prompt.strip():
        text = compose_document_text(
            template.output_format,
            prompt,
            template.body or "",
            kb_slugs,
        )
    else:
        text = render_body(template, values, strict=strict)
    slug = re.sub(r"[^A-Za-zА-Яа-я0-9._-]+", "_", template.name).strip("_") or "document"
    return {
        "mode": "draft",
        "template_id": template.pk,
        "template_name": template.name,
        "output_format": template.output_format,
        "format_label": FORMAT_LABELS.get(template.output_format, template.output_format),
        "filename": f"{slug}.{template.output_format}",
        "text": text,
    }


def file_response(
    template: AssistantDocumentTemplate,
    values: Mapping[str, Any],
    *,
    prompt: str = "",
    kb_slugs: Sequence[str] | None = None,
) -> HttpResponse:
    data, filename, content_type = build_document(
        template,
        values,
        prompt=prompt,
        kb_slugs=kb_slugs,
    )
    ascii_name = filename if filename.isascii() else f"document.{template.output_format}"
    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(filename)}"
    )
    response["X-Document-Filename"] = quote(filename, safe="._-")
    return response


def validation_error(exc: Exception) -> JsonResponse:
    return JsonResponse(
        {
            "error": "validation_error",
            "details": {"request": [str(exc)]},
        },
        status=400,
    )
