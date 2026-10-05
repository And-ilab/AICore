"""Personal OCR templates (P6-03a). User layer only — not the bank catalog."""

from __future__ import annotations

import re
from typing import Any, Mapping

from django.db import IntegrityError, transaction
from django.utils import timezone

from ocr.models import OcrJob, OcrUserTemplate

NAME_MIN = 1
NAME_MAX = 80
NAME_TAKEN = "такое имя уже есть"
REVIEW_BLOCKED = "сначала исправьте и утвердите"
FIELD_KEY_RE = re.compile(r"^[A-Za-zА-Яа-яЁё0-9_][A-Za-zА-Яа-яЁё0-9_.\-]{0,63}$")
ALLOWED_FIELD_TYPES = frozenset({"string", "date", "number"})
MAX_TEMPLATE_FIELDS = 40
MIN_CONFIDENCE = 0.6
_DATE_RE = re.compile(
    r"^\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}$|^\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}$"
)
_NUMBER_RE = re.compile(r"^[\d\s.,\-]+$")
_DOC_TITLES = {
    "passport": "Паспорт",
    "account_statement": "Банковская выписка",
    "loan_agreement": "Договор",
}


class UserTemplateError(ValueError):
    """Invalid personal template request."""


class UserTemplateNotFound(UserTemplateError):
    """Missing or not owned by the caller."""


class UserTemplateNameTaken(UserTemplateError):
    """Case-insensitive name collision in the user layer."""

    def __init__(self, message: str = NAME_TAKEN) -> None:
        super().__init__(message)


def name_key(name: str) -> str:
    return (name or "").strip().casefold()


def normalize_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if len(name) < NAME_MIN or len(name) > NAME_MAX:
        raise UserTemplateError(f"name must be {NAME_MIN}–{NAME_MAX} characters")
    return name


def serialize_user_template(template: OcrUserTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "name": template.name,
        "fields": list(template.fields or []),
        "source_job_id": template.source_job_id or "",
        "source_file": template.source_file or "",
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
    }


def field_schema_for(template: OcrUserTemplate) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for item in template.fields or []:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        fields[key] = {
            "type": str(item.get("type") or "string"),
            "label": str(item.get("label") or key),
            "pattern": str(item.get("pattern") or ""),
        }
    return {"fields": fields}


def schema_keys(template: OcrUserTemplate) -> list[str]:
    keys: list[str] = []
    for item in template.fields or []:
        if not isinstance(item, Mapping):
            continue
        key = str(item.get("key") or "").strip()
        if key and key not in keys:
            keys.append(key)
    return keys


def list_for_user(user: Any) -> list[dict[str, Any]]:
    owner_id = getattr(user, "pk", None)
    if not owner_id:
        return []
    return [
        serialize_user_template(item)
        for item in OcrUserTemplate.objects.filter(owner_id=owner_id)
    ]


def get_owned(template_id: int, user: Any) -> OcrUserTemplate:
    owner_id = getattr(user, "pk", None)
    try:
        template = OcrUserTemplate.objects.get(pk=template_id)
    except OcrUserTemplate.DoesNotExist as exc:
        raise UserTemplateNotFound("template not found") from exc
    if template.owner_id != owner_id:
        raise UserTemplateNotFound("template not found")
    return template


def _unwrap_field(raw: Any) -> tuple[str, float, str]:
    if raw is None:
        return "", 0.0, ""
    if isinstance(raw, Mapping):
        value = raw.get("value")
        conf = raw.get("confidence")
        label = str(raw.get("label") or "").strip()
        try:
            confidence = float(conf) if conf is not None else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence > 1:
            confidence = confidence / 100.0
        return ("" if value is None else str(value).strip()), confidence, label
    return str(raw).strip(), 0.0, ""


def _iter_result_fields(result: Mapping[str, Any]) -> list[tuple[str, str, float, str]]:
    raw = result.get("normalized_fields") or result.get("fields") or {}
    if not isinstance(raw, Mapping):
        return []
    items: list[tuple[str, str, float, str]] = []
    for key, payload in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        value, confidence, label = _unwrap_field(payload)
        items.append((name, value, confidence, label))
    return items


def _job_approved(job: OcrJob, result: Mapping[str, Any]) -> bool:
    status = str(job.validation_status or result.get("validation_status") or "")
    if status in {"valid", "approved"}:
        return True
    hitl = result.get("hitl")
    return isinstance(hitl, Mapping) and bool(hitl.get("approved"))


def _infer_type(value: str) -> str:
    if _DATE_RE.match(value):
        return "date"
    if value and _NUMBER_RE.match(value) and any(ch.isdigit() for ch in value):
        return "number"
    return "string"


def _soft_pattern(value: str, field_type: str) -> str:
    text = value.strip()
    if field_type == "date":
        return r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}"
    if field_type == "number":
        return r"[\d\s.,\-]+"
    if 1 <= len(text) <= 40 and re.fullmatch(r"[\w.\-/\s]+", text, re.UNICODE):
        return re.escape(text)
    return ""


def _humanize_key(key: str) -> str:
    return key.replace("_", " ").strip() or key


def suggest_name(job: OcrJob, result: Mapping[str, Any] | None = None) -> str:
    payload = result or {}
    doc_type = str(payload.get("document_type") or job.document_type or "").strip()
    title = _DOC_TITLES.get(doc_type)
    if not title:
        for _key, value, _conf, label in _iter_result_fields(payload):
            if value:
                title = (label or _humanize_key(_key))[:40]
                break
    if not title:
        title = "Документ"
    stamp = timezone.now().date().isoformat()
    return f"{title} · {stamp}"[:NAME_MAX]


def fields_from_job(job: OcrJob, result: Mapping[str, Any]) -> list[dict[str, str]]:
    approved = _job_approved(job, result)
    collected: list[dict[str, str]] = []
    blocking = False
    for key, value, confidence, label in _iter_result_fields(result):
        valid = bool(value) and (approved or confidence >= MIN_CONFIDENCE)
        if not valid:
            blocking = True
            continue
        field_type = _infer_type(value)
        collected.append(
            {
                "key": key,
                "label": label or _humanize_key(key),
                "type": field_type,
                "pattern": _soft_pattern(value, field_type),
            }
        )
    if not collected:
        raise UserTemplateError(REVIEW_BLOCKED)
    if not approved and blocking:
        raise UserTemplateError(REVIEW_BLOCKED)
    return collected


def _load_job_for_user(job_id: str, user: Any) -> tuple[OcrJob, dict[str, Any]]:
    try:
        job = OcrJob.objects.get(pk=job_id)
    except OcrJob.DoesNotExist as exc:
        raise UserTemplateNotFound("job not found") from exc
    actor = getattr(user, "username", "") or ""
    if job.created_by and actor and job.created_by != actor:
        raise UserTemplateNotFound("job not found")
    if job.status != OcrJob.STATUS_COMPLETED:
        raise UserTemplateError(REVIEW_BLOCKED)
    from ocr.pipeline import load_result

    return job, load_result(job)


def create_from_job(user: Any, *, job_id: str, name: str) -> dict[str, Any]:
    owner_id = getattr(user, "pk", None)
    if not owner_id:
        raise UserTemplateError("authentication required")
    job, result = _load_job_for_user(str(job_id or "").strip(), user)
    title = normalize_name(name or suggest_name(job, result))
    key = name_key(title)
    if OcrUserTemplate.objects.filter(owner_id=owner_id, name_key=key).exists():
        raise UserTemplateNameTaken()
    fields = fields_from_job(job, result)
    try:
        with transaction.atomic():
            template = OcrUserTemplate.objects.create(
                owner_id=owner_id,
                name=title,
                name_key=key,
                fields=fields,
                source_job_id=job.job_id,
                source_file=job.filename,
            )
    except IntegrityError as exc:
        raise UserTemplateNameTaken() from exc
    return serialize_user_template(template)


def normalize_fields(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        raise UserTemplateError("fields must be an array")
    if len(raw) > MAX_TEMPLATE_FIELDS:
        raise UserTemplateError(f"не больше {MAX_TEMPLATE_FIELDS} полей")
    seen: set[str] = set()
    fields: list[dict[str, str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise UserTemplateError(f"поле {index}: ожидается объект")
        key = str(item.get("key") or "").strip()
        label = str(item.get("label") or "").strip() or key
        field_type = str(item.get("type") or "string").strip().lower()
        pattern = str(item.get("pattern") or "").strip()
        if not key or not FIELD_KEY_RE.match(key):
            raise UserTemplateError(
                f"поле {index}: ключ 1–64 символа (буквы, цифры, _ . -)"
            )
        if key.casefold() in seen:
            raise UserTemplateError(f"ключ «{key}» уже есть в шаблоне")
        if field_type not in ALLOWED_FIELD_TYPES:
            raise UserTemplateError("тип поля: string, date или number")
        if len(label) > 80:
            raise UserTemplateError("подпись поля не длиннее 80 символов")
        if len(pattern) > 200:
            raise UserTemplateError("шаблон поля не длиннее 200 символов")
        seen.add(key.casefold())
        fields.append(
            {
                "key": key,
                "label": label,
                "type": field_type,
                "pattern": pattern,
            }
        )
    if not fields:
        raise UserTemplateError("в шаблоне должно быть хотя бы одно поле")
    return fields


def rename_template(template_id: int, user: Any, name: str) -> dict[str, Any]:
    return update_template(template_id, user, name=name)


def update_template(
    template_id: int,
    user: Any,
    *,
    name: str | None = None,
    fields: Any | None = None,
) -> dict[str, Any]:
    template = get_owned(template_id, user)
    if name is None and fields is None:
        raise UserTemplateError("укажите name или fields")
    update_fields = ["updated_at"]
    if name is not None:
        title = normalize_name(name)
        key = name_key(title)
        clash = (
            OcrUserTemplate.objects.filter(owner_id=template.owner_id, name_key=key)
            .exclude(pk=template.pk)
            .exists()
        )
        if clash:
            raise UserTemplateNameTaken()
        template.name = title
        template.name_key = key
        update_fields.extend(["name", "name_key"])
    if fields is not None:
        template.fields = normalize_fields(fields)
        update_fields.append("fields")
    try:
        with transaction.atomic():
            template.save(update_fields=update_fields)
    except IntegrityError as exc:
        raise UserTemplateNameTaken() from exc
    return serialize_user_template(template)


def delete_template(template_id: int, user: Any) -> None:
    template = get_owned(template_id, user)
    template.delete()
