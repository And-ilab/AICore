"""Template Registry: YAML seed + DB overrides for OCR document types."""

from __future__ import annotations

from typing import Any, Mapping

from django.db import transaction
from django.utils import timezone

from ocr.models import OcrDocumentTemplate, OcrTemplateSample
from ocr.validation import DEFAULT_RULES_PATH, ValidationConfigError, _load_rules


class TemplateRegistryError(ValueError):
    """Invalid template admin operation."""


_PASSPORT_OPERATOR_FIELDS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("surname", {"type": "string", "min_length": 2, "max_length": 80}),
    ("given_name", {"type": "string", "min_length": 2, "max_length": 80}),
    ("series", {"type": "string", "pattern": r"^([A-ZА-Я]{2}|\d{2}\s?\d{2})$"}),
    ("number", {"type": "string", "pattern": r"^\d{6,7}$"}),
    ("birth_date", {"type": "date", "formats": ["%d.%m.%Y", "%Y-%m-%d"]}),
    ("issue_date", {"type": "date", "formats": ["%d.%m.%Y", "%Y-%m-%d"]}),
)

_PASSPORT_REQUIRED = ("surname", "given_name", "number")


def ensure_passport_identity_schema(
    field_schema: Mapping[str, Any] | None,
    required_fields: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Keep the operator passport slots; drop extra keys like expiry/nationality."""
    schema = dict(field_schema or {})
    ordered: dict[str, Any] = {}
    for key, spec in _PASSPORT_OPERATOR_FIELDS:
        current = schema.get(key)
        ordered[key] = dict(current) if isinstance(current, Mapping) else dict(spec)
    required = [key for key in _PASSPORT_REQUIRED if key in ordered]
    extra = [key for key in (required_fields or []) if key in ordered and key not in required]
    return ordered, required + extra


def _persist_passport_identity(template: OcrDocumentTemplate) -> OcrDocumentTemplate:
    if template.doc_type != "passport":
        return template
    schema, required = ensure_passport_identity_schema(
        template.field_schema, list(template.required_fields or [])
    )
    if schema == (template.field_schema or {}) and required == list(
        template.required_fields or []
    ):
        return template
    template.field_schema = schema
    template.required_fields = required
    template.save(update_fields=["field_schema", "required_fields", "updated_at"])
    return template


def seed_templates_from_yaml(*, force: bool = False) -> list[dict[str, Any]]:
    """Ensure DB templates exist for every YAML document_type."""
    rules = _load_rules(DEFAULT_RULES_PATH)
    created: list[dict[str, Any]] = []
    for name, spec in rules["document_types"].items():
        defaults = {
            "title": str(spec.get("title") or name),
            "template_version": int(spec.get("template_version") or 1),
            "status": OcrDocumentTemplate.STATUS_PUBLISHED,
            "required_fields": list(spec.get("required_fields") or []),
            "field_schema": dict(spec.get("fields") or {}),
            "confidence_min": float(spec.get("confidence_min") or 0.6),
            "published_at": timezone.now(),
            "owner": "system",
        }
        obj, was_created = OcrDocumentTemplate.objects.get_or_create(
            doc_type=name,
            defaults=defaults,
        )
        if force and not was_created:
            for key, value in defaults.items():
                setattr(obj, key, value)
            obj.save()
        created.append(template_to_dict(obj, include_samples=False))
    return created


def list_templates(*, include_drafts: bool = True) -> list[dict[str, Any]]:
    if not OcrDocumentTemplate.objects.exists():
        try:
            seed_templates_from_yaml()
        except ValidationConfigError:
            return []
    qs = OcrDocumentTemplate.objects.all()
    if not include_drafts:
        qs = qs.filter(status=OcrDocumentTemplate.STATUS_PUBLISHED)
    return [
        template_to_dict(_persist_passport_identity(item), include_samples=True)
        for item in qs
    ]


def get_template(doc_type: str) -> OcrDocumentTemplate:
    if not OcrDocumentTemplate.objects.exists():
        seed_templates_from_yaml()
    try:
        template = OcrDocumentTemplate.objects.get(doc_type=doc_type)
    except OcrDocumentTemplate.DoesNotExist as exc:
        raise TemplateRegistryError(f"Unknown doc_type: {doc_type}") from exc
    return _persist_passport_identity(template)


def template_schema_for(doc_type: str) -> dict[str, Any]:
    template = get_template(doc_type)
    fields = dict(template.field_schema or {})
    required = list(template.required_fields or [])
    if doc_type == "passport":
        fields, required = ensure_passport_identity_schema(fields, required)
    return {
        "doc_type": template.doc_type,
        "title": template.title,
        "template_version": str(template.template_version),
        "required_fields": required,
        "fields": fields,
        "confidence_min": float(template.confidence_min),
    }


def template_to_dict(
    template: OcrDocumentTemplate,
    *,
    include_samples: bool = False,
) -> dict[str, Any]:
    if template.doc_type == "passport":
        field_schema, required_fields = ensure_passport_identity_schema(
            template.field_schema, list(template.required_fields or [])
        )
    else:
        field_schema = dict(template.field_schema or {})
        required_fields = list(template.required_fields or [])
    payload: dict[str, Any] = {
        "id": template.pk,
        "doc_type": template.doc_type,
        "title": template.title,
        "description": template.description,
        "template_version": template.template_version,
        "status": template.status,
        "required_fields": required_fields,
        "field_schema": field_schema,
        "confidence_min": float(template.confidence_min),
        "sample_prompt": template.sample_prompt,
        "owner": template.owner,
        "published_at": (
            template.published_at.isoformat() if template.published_at else None
        ),
        "updated_at": (
            template.updated_at.isoformat() if template.updated_at else None
        ),
        "sample_count": template.samples.count(),
    }
    if include_samples:
        payload["samples"] = [
            {
                "id": sample.pk,
                "filename": sample.filename,
                "content_type": sample.content_type,
                "ocr_text": sample.ocr_text,
                "expected_fields": dict(sample.expected_fields or {}),
                "notes": sample.notes,
                "created_by": sample.created_by,
                "created_at": (
                    sample.created_at.isoformat() if sample.created_at else None
                ),
            }
            for sample in template.samples.all()[:50]
        ]
    return payload


def upsert_template(payload: Mapping[str, Any], *, actor: str = "") -> dict[str, Any]:
    doc_type = str(payload.get("doc_type") or "").strip()
    if not doc_type:
        raise TemplateRegistryError("doc_type is required")
    title = str(payload.get("title") or doc_type).strip()
    required = payload.get("required_fields") or []
    if not isinstance(required, list):
        raise TemplateRegistryError("required_fields must be a list")
    field_schema = payload.get("field_schema") or payload.get("fields") or {}
    if not isinstance(field_schema, Mapping):
        raise TemplateRegistryError("field_schema must be an object")

    with transaction.atomic():
        template, created = OcrDocumentTemplate.objects.select_for_update().get_or_create(
            doc_type=doc_type,
            defaults={
                "title": title,
                "owner": actor[:150],
            },
        )
        if "title" in payload:
            template.title = title
        if "description" in payload:
            template.description = str(payload.get("description") or "")
        if "required_fields" in payload:
            template.required_fields = list(required)
        if "field_schema" in payload or "fields" in payload:
            template.field_schema = dict(field_schema)
        if "confidence_min" in payload:
            template.confidence_min = float(payload["confidence_min"])
        if "sample_prompt" in payload:
            template.sample_prompt = str(payload.get("sample_prompt") or "")
        if actor:
            template.owner = actor[:150]
        bump = bool(payload.get("bump_version"))
        publish = bool(payload.get("publish"))
        if bump or publish:
            template.template_version = int(template.template_version or 1) + (
                1 if not created and bump else 0
            )
            if created and template.template_version < 1:
                template.template_version = 1
        if publish:
            template.status = OcrDocumentTemplate.STATUS_PUBLISHED
            template.published_at = timezone.now()
            if not bump and not created:
                template.template_version = int(template.template_version or 1) + 1
        elif "status" in payload:
            status = str(payload.get("status") or "").strip()
            if status not in {
                OcrDocumentTemplate.STATUS_DRAFT,
                OcrDocumentTemplate.STATUS_PUBLISHED,
                OcrDocumentTemplate.STATUS_ARCHIVED,
            }:
                raise TemplateRegistryError(f"Invalid status: {status}")
            template.status = status
            if status == OcrDocumentTemplate.STATUS_PUBLISHED:
                template.published_at = timezone.now()
        template.save()
    return template_to_dict(template, include_samples=True)


def add_template_sample(
    doc_type: str,
    *,
    filename: str,
    ocr_text: str,
    expected_fields: Mapping[str, Any] | None = None,
    content_type: str = "",
    notes: str = "",
    actor: str = "",
    object_key: str = "",
) -> dict[str, Any]:
    template = get_template(doc_type)
    sample = OcrTemplateSample.objects.create(
        template=template,
        filename=filename[:255],
        content_type=(content_type or "")[:128],
        object_key=object_key[:512],
        ocr_text=ocr_text or "",
        expected_fields=dict(expected_fields or {}),
        notes=notes or "",
        created_by=actor[:150],
    )
    if ocr_text and not template.sample_prompt:
        template.sample_prompt = ocr_text[:4000]
        template.save(update_fields=["sample_prompt", "updated_at"])
    return {
        "id": sample.pk,
        "doc_type": template.doc_type,
        "filename": sample.filename,
        "expected_fields": dict(sample.expected_fields or {}),
        "ocr_text": sample.ocr_text,
    }
