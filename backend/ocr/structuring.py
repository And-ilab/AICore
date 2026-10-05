"""OCR text → structured fields via extractor + ModelGateway docs_ocr."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

from ocr.extraction import extract_fields, fields_as_plain
from ocr.page_templates import (
    canonical_field_key,
    collapse_extracted_fields,
    is_form_header_label,
    is_usable_field_key,
)

logger = logging.getLogger(__name__)

_KNOWN_DOC_TYPES = frozenset(
    {
        "passport",
        "payment_order",
        "payment_receipt",
        "account_statement",
        "loan_agreement",
        "banking_application",
        "contract",
        "invoice",
    }
)
_LLM_CONFIDENCE_CAP = 0.80
_LLM_CONFIDENCE_DEFAULT = 0.72

_SYSTEM_PROMPT = (
    "Extract every labeled value from OCR text of any document. "
    "Reply with a single JSON object only, no markdown. "
    "Schema: {\"document_type\": \"<passport, payment_order, "
    "payment_receipt, account_statement, loan_agreement, "
    "banking_application, contract, invoice, unknown>\", "
    "\"fields\": {\"<label>\": {\"value\": \"<string>\", "
    "\"confidence\": <0..1>}}}. "
    "A field is a clear 'Label: value' pair, table row, or two-column line. "
    "Use the original label text as the field key (Russian or English). "
    "Do not invent fields from watermarks, stamps, headers, or consecutive "
    "OCR fragments. Skip a token if it is not a real label. "
    "If field_schema is provided, extract ONLY those keys. "
    "Do not invent extra fields. "
    "Use only values present in the OCR text or an obvious OCR fix. "
    "Leave a field out instead of guessing. "
    "Never put a region or stamp into full_name."
)


def _parse_json_content(content: str) -> dict[str, Any] | None:
    text = (content or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _normalize_llm_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name or is_form_header_label(name) or not is_usable_field_key(name):
            continue
        name = canonical_field_key(name) or name
        if isinstance(value, Mapping) and "value" in value:
            text = value.get("value")
            if text is None or str(text).strip() == "":
                continue
            try:
                confidence = float(value.get("confidence") or _LLM_CONFIDENCE_DEFAULT)
            except (TypeError, ValueError):
                confidence = _LLM_CONFIDENCE_DEFAULT
            payload = {
                "value": str(text).strip(),
                "confidence": round(min(_LLM_CONFIDENCE_CAP, max(0.0, confidence)), 4),
                "source": "llm",
                "label": str(value.get("label") or name).strip(),
            }
            normalized[name] = payload
            continue
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        normalized[name] = {
            "value": text,
            "confidence": _LLM_CONFIDENCE_DEFAULT,
            "source": "llm",
            "label": name,
        }
    return normalized


def _merge_field_maps(
    primary: Mapping[str, Any],
    secondary: Mapping[str, Any],
) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in secondary.items():
        if key not in merged:
            merged[key] = value
            continue
        left = merged[key]
        right = value
        left_conf = (
            float(left.get("confidence") or 0)
            if isinstance(left, Mapping)
            else 0.0
        )
        right_conf = (
            float(right.get("confidence") or 0)
            if isinstance(right, Mapping)
            else 0.0
        )
        if right_conf > left_conf:
            merged[key] = right
    return merged


def structure_document(
    ocr_text: str,
    *,
    filename: str = "",
    document_type_hint: str | None = None,
    field_schema: Mapping[str, Any] | None = None,
    use_gateway: bool = True,
    pages: list[str] | None = None,
) -> dict[str, Any]:
    """Return document_type + fields(+confidence) + optional LLM proposal."""
    doc_type, extracted = extract_fields(
        ocr_text,
        document_type=document_type_hint,
        filename=filename,
        pages=pages,
        field_schema=field_schema,
    )
    llm_proposal: dict[str, Any] | None = None
    llm_fields: dict[str, Any] = {}

    if use_gateway:
        try:
            from core.model_gateway import ModelGateway

            schema_hint = field_schema or {}
            user_payload = {
                "filename": filename,
                "document_type_hint": doc_type,
                "ocr_text": ocr_text,
                "field_schema": schema_hint,
            }
            gateway = ModelGateway.from_registry()
            completion = gateway.chat(
                "docs_ocr",
                [
                    {
                        "role": "system",
                        "content": _SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            user_payload,
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            content = (
                completion.get("choices", [{}])[0]
                .get("message", {})
                .get("content")
            )
            if isinstance(content, str):
                llm_proposal = _parse_json_content(content)
                if llm_proposal:
                    proposed_type = str(
                        llm_proposal.get("document_type") or ""
                    ).strip()
                    if (
                        proposed_type in _KNOWN_DOC_TYPES
                        and doc_type in {"unknown", "", None}
                    ):
                        doc_type = proposed_type
                    raw_fields = llm_proposal.get("fields") or {}
                    if isinstance(raw_fields, Mapping):
                        llm_fields = _normalize_llm_fields(raw_fields)
        except Exception as exc:
            logger.warning("docs_ocr LLM structuring skipped: %s", exc)
            llm_proposal = None

    fields = collapse_extracted_fields(
        _merge_field_maps(fields_as_plain(extracted), llm_fields)
    )
    schema_keys: set[str] = set()
    if isinstance(field_schema, Mapping):
        nested = field_schema.get("fields")
        raw_fields = nested if isinstance(nested, Mapping) else field_schema
        if isinstance(raw_fields, Mapping):
            schema_keys = {str(name) for name in raw_fields if name != "fields"}
    from ocr.extraction import is_open_ended_doc_type

    hint = (document_type_hint or "").strip()
    if hint and not is_open_ended_doc_type(hint):
        doc_type = hint
    if schema_keys:
        fields = {
            key: value
            for key, value in fields.items()
            if key in schema_keys or canonical_field_key(key) in schema_keys
        }
        remapped: dict[str, Any] = {}
        for key, value in fields.items():
            target = key if key in schema_keys else (canonical_field_key(key) or key)
            if target in schema_keys:
                remapped[target] = value
        fields = remapped
    return {
        "document_type": doc_type,
        "fields": fields,
        "extractor_fields": fields_as_plain(extracted),
        "llm_proposal": llm_proposal,
    }
