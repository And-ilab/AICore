"""Export validated OCR payloads as JSON/CSV/PDF/DOCX (IV.8 / FR-OCR-23 / DOC-T-08)."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any, Mapping

from ocr.page_templates import FIELD_LABELS
from ocr.validation import (
    STATUS_VALID,
    ValidationRequestError,
    ValidationResult,
    assert_downstream_ready,
)

EXPORT_JSON = "json"
EXPORT_CSV = "csv"
EXPORT_PDF = "pdf"
EXPORT_DOCX = "docx"
EXPORT_FORMATS = frozenset({EXPORT_JSON, EXPORT_CSV, EXPORT_PDF, EXPORT_DOCX})

# Same Russian titles as the review panel to the right of the scan.
_UI_FIELD_TITLES: dict[str, str] = {
    "surname": "Фамилия",
    "given_name": "Имя",
    "patronymic": "Отчество",
    "series": "Серия паспорта",
    "number": "Номер",
    "full_name": "ФИО",
    "issue_date": "Дата выдачи",
    "birth_date": "Дата рождения",
    "expiry_date": "Срок действия",
    "personal_number": "Личный номер",
    "nationality": "Гражданство",
    "address": "Адрес / прописка",
    "registration_date": "Дата регистрации",
    "issued_by": "Кем выдан",
    "birth_place": "Место рождения",
    "document_number": "Номер документа",
    "date": "Дата",
    "payer": "Плательщик",
    "beneficiary": "Получатель",
    "amount": "Сумма",
    "purpose": "Назначение",
    "currency": "Валюта",
    "product": "Продукт",
    "application_date": "Дата заявления",
    "application_number": "Номер заявления",
    "account_number": "Счёт",
    "opening_balance": "Входящий остаток",
    "closing_balance": "Исходящий остаток",
    "period": "Период",
    "agreement_number": "Номер договора",
    "agreement_date": "Дата договора",
    "principal": "Сумма кредита",
    "interest_rate": "Процентная ставка",
    "term": "Срок",
    "operation_id": "Номер операции",
    "operation_date": "Дата операции",
    "sex": "Пол",
    "inn": "ИНН",
}

_HIDDEN_EXPORT_KEYS = frozenset({"full_name", "signature_present", "title", "status"})
_EMPTY_VALUES = frozenset({"", "—", "-", "–", "null", "none", "none."})


def normalize_export_format(value: str | None) -> str:
    fmt = (value or EXPORT_JSON).strip().lower()
    if fmt not in EXPORT_FORMATS:
        raise ValidationRequestError("format must be json|csv|pdf|docx")
    return fmt


def export_filename(result: ValidationResult, export_format: str) -> str:
    doc = result.document_id or "document"
    job = result.job_id or "adhoc"
    return f"ocr-validated_{result.document_type}_{doc}_{job}.{export_format}"


def _plain_value(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return "да" if raw else "нет"
    if isinstance(raw, Mapping):
        return _plain_value(raw.get("value", raw.get("normalized_value")))
    text = str(raw).strip()
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return f"{iso.group(3)}.{iso.group(2)}.{iso.group(1)}"
    return text


def _russian_field_title(key: str) -> str:
    if key in _UI_FIELD_TITLES:
        return _UI_FIELD_TITLES[key]
    aliases = FIELD_LABELS.get(key)
    if aliases:
        return aliases[0]
    return ""


def _schema_field_keys(document_type: str) -> list[str]:
    from ocr.validation import list_document_types

    for item in list_document_types():
        if item.get("doc_type") == document_type:
            schema = item.get("field_schema") or {}
            return [str(name) for name in schema]
    return []


def labeled_export_lines(result: ValidationResult) -> list[str]:
    """Russian «ключ: значение» rows, template fields only — same as the review panel."""
    raw = result.fields if isinstance(result.fields, Mapping) else {}
    normalized = (
        result.normalized_fields if isinstance(result.normalized_fields, Mapping) else {}
    )
    schema_keys = _schema_field_keys(result.document_type)
    candidate_keys = schema_keys or [
        key
        for key in list(normalized) + [str(name) for name in raw]
        if _russian_field_title(str(key))
    ]
    seen: set[str] = set()
    lines: list[str] = []
    for key in candidate_keys:
        name = str(key)
        if name in _HIDDEN_EXPORT_KEYS or name in seen:
            continue
        seen.add(name)
        label = _russian_field_title(name)
        if not label:
            continue
        value = _plain_value(raw.get(name))
        if not value:
            value = _plain_value(normalized.get(name))
        if value.casefold() in _EMPTY_VALUES:
            continue
        lines.append(f"{label}: {value}")
    return lines


def build_json_export(
    result: ValidationResult,
    *,
    require_valid: bool = True,
) -> bytes:
    if require_valid:
        assert_downstream_ready(result)
    payload = result.as_dict()
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def build_csv_export(
    result: ValidationResult,
    *,
    require_valid: bool = True,
) -> bytes:
    if require_valid:
        assert_downstream_ready(result)
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "document_type",
            "status",
            "field",
            "value",
            "job_id",
            "document_id",
            "template_version",
            "validator_version",
        ]
    )
    for name, value in result.normalized_fields.items():
        writer.writerow(
            [
                result.document_type,
                result.status,
                name,
                value,
                result.job_id or "",
                result.document_id or "",
                result.template_version,
                result.validator_version,
            ]
        )
    return buffer.getvalue().encode("utf-8")


def build_pdf_export(
    result: ValidationResult,
    *,
    require_valid: bool = True,
) -> bytes:
    if require_valid:
        assert_downstream_ready(result)
    lines = [
        f"OCR HITL · {result.document_type}",
        f"status: {result.status}",
        f"job: {result.job_id or '—'}",
        "",
    ]
    fields = result.normalized_fields or {}
    if not fields and isinstance(result.fields, Mapping):
        for key, raw in result.fields.items():
            if isinstance(raw, Mapping) and "value" in raw:
                fields[key] = raw.get("value")
            else:
                fields[key] = raw
    for name, value in fields.items():
        lines.append(f"{name}: {value}")
    if not fields:
        lines.append("(no fields)")
    from assistant.docgen import _pdf_bytes

    return _pdf_bytes("\n".join(str(item) for item in lines))


def build_docx_export(
    result: ValidationResult,
    *,
    require_valid: bool = True,
) -> bytes:
    if require_valid:
        assert_downstream_ready(result)
    from assistant.docgen import _docx_bytes

    lines = labeled_export_lines(result)
    return _docx_bytes("\n".join(lines))


def build_export(
    result: ValidationResult,
    export_format: str,
    *,
    require_valid: bool = True,
) -> tuple[bytes, str]:
    fmt = normalize_export_format(export_format)
    if fmt == EXPORT_CSV:
        payload = build_csv_export(result, require_valid=require_valid)
        content_type = "text/csv; charset=utf-8"
    elif fmt == EXPORT_PDF:
        payload = build_pdf_export(result, require_valid=require_valid)
        content_type = "application/pdf"
    elif fmt == EXPORT_DOCX:
        payload = build_docx_export(result, require_valid=require_valid)
        content_type = (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    else:
        payload = build_json_export(result, require_valid=require_valid)
        content_type = "application/json; charset=utf-8"
    return payload, content_type


def validation_result_from_mapping(payload: Mapping[str, Any]) -> ValidationResult:
    """Rebuild ValidationResult from a previously validated dict (tests/API)."""
    from ocr.validation import FieldAnomaly

    validation = payload.get("validation") or {}
    anomalies = [
        FieldAnomaly(
            str(item.get("field") or ""),
            str(item.get("code") or ""),
            str(item.get("message") or ""),
        )
        for item in (validation.get("anomalies") or [])
        if isinstance(item, Mapping)
    ]
    return ValidationResult(
        document_type=str(payload.get("document_type") or ""),
        status=str(payload.get("status") or STATUS_VALID),
        fields=dict(payload.get("raw_fields") or payload.get("fields") or {}),
        normalized_fields=dict(payload.get("fields") or {}),
        missing_required_fields=list(
            validation.get("missing_required_fields") or []
        ),
        anomalies=anomalies,
        rejected_fields=list(payload.get("rejected_fields") or []),
        template_version=str(validation.get("template_version") or "1"),
        validator_version=str(validation.get("validator_version") or "1.0"),
        job_id=payload.get("job_id"),
        document_id=payload.get("document_id"),
        document_sha256=payload.get("document_sha256"),
    )
