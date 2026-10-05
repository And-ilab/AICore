"""Deterministic field validation per doc_type (IV.8 / FR-OCR-14 / DOC-T-04)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

import yaml

DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "ocr_validation_rules.yaml"
)

STATUS_VALID = "valid"
STATUS_PENDING_REVIEW = "pending_review"
STATUS_REJECTED = "rejected"


class ValidationConfigError(ValueError):
    """Rules file is missing or malformed."""


class ValidationRequestError(ValueError):
    """Caller sent an unusable validation payload."""


@dataclass(frozen=True)
class FieldAnomaly:
    field: str
    code: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "code": self.code,
            "message": self.message,
        }


@dataclass
class ValidationResult:
    document_type: str
    status: str
    fields: dict[str, Any]
    normalized_fields: dict[str, Any]
    missing_required_fields: list[str] = field(default_factory=list)
    anomalies: list[FieldAnomaly] = field(default_factory=list)
    rejected_fields: list[str] = field(default_factory=list)
    template_version: str = "1"
    validator_version: str = "1.0"
    job_id: str | None = None
    document_id: str | None = None
    document_sha256: str | None = None
    acceptance: tuple[str, ...] = ("DOC-T-04", "FR-OCR-14")

    @property
    def is_valid(self) -> bool:
        return self.status == STATUS_VALID

    def as_dict(self) -> dict[str, Any]:
        validated_at = datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
        return {
            "schema_version": "1.0",
            "job_id": self.job_id,
            "document_id": self.document_id,
            "document_sha256": self.document_sha256,
            "document_type": self.document_type,
            "status": self.status,
            "fields": dict(self.normalized_fields),
            "raw_fields": dict(self.fields),
            "rejected_fields": list(self.rejected_fields),
            "validation": {
                "validator_version": self.validator_version,
                "template_version": self.template_version,
                "missing_required_fields": list(self.missing_required_fields),
                "anomalies": [item.as_dict() for item in self.anomalies],
                "validated_at": validated_at,
                "downstream_allowed": self.is_valid,
            },
            "provenance": {
                "section": "IV.8",
                "acceptance": list(self.acceptance),
                "rules_source": "ocr_validation_rules.yaml",
            },
        }


def _load_rules(path: Path = DEFAULT_RULES_PATH) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationConfigError(f"Rules not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValidationConfigError(f"Invalid rules YAML: {path}") from exc
    if not isinstance(payload, Mapping):
        raise ValidationConfigError("Rules root must be a mapping")
    types = payload.get("document_types")
    if not isinstance(types, Mapping) or not types:
        raise ValidationConfigError("document_types mapping is required")
    return dict(payload)


def list_document_types(path: Path = DEFAULT_RULES_PATH) -> list[dict[str, Any]]:
    rules = _load_rules(path)
    items: list[dict[str, Any]] = []
    for name, spec in rules["document_types"].items():
        items.append(
            {
                "doc_type": name,
                "title": spec.get("title") or name,
                "template_version": str(spec.get("template_version") or "1"),
                "required_fields": list(spec.get("required_fields") or []),
                "field_schema": dict(spec.get("fields") or {}),
                "confidence_min": spec.get("confidence_min"),
            }
        )
    return items


def _unwrap_value(raw: Any) -> tuple[Any, float | None]:
    if isinstance(raw, Mapping):
        value = raw.get("value", raw.get("normalized_value"))
        confidence = raw.get("confidence")
        conf = float(confidence) if confidence is not None else None
        return value, conf
    return raw, None


def _parse_money(value: Any) -> Decimal:
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace("\u00a0", "")
    text = text.replace(",", ".")
    text = re.sub(r"[^0-9.\-]", "", text)
    return Decimal(text)


def _parse_date(value: Any, formats: list[str]) -> str:
    text = str(value).strip()
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"date does not match formats {formats}")


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "да", "истина"}:
        return True
    if text in {"0", "false", "no", "n", "нет", "ложь"}:
        return False
    raise ValueError("boolean expected")


def _check_field(
    name: str,
    rule: Mapping[str, Any],
    raw: Any,
    *,
    confidence_min: float,
) -> tuple[Any | None, list[FieldAnomaly], bool]:
    """Return (normalized, anomalies, rejected)."""
    anomalies: list[FieldAnomaly] = []
    value, confidence = _unwrap_value(raw)

    if value is None or (isinstance(value, str) and not value.strip()):
        return None, [
            FieldAnomaly(name, "empty", "Field value is empty")
        ], True

    if confidence is not None and confidence < confidence_min:
        anomalies.append(
            FieldAnomaly(
                name,
                "low_confidence",
                f"Confidence {confidence:.2f} below minimum {confidence_min:.2f}",
            )
        )

    field_type = str(rule.get("type") or "string")
    normalized: Any = value
    try:
        if field_type == "string":
            normalized = str(value).strip()
            min_len = rule.get("min_length")
            max_len = rule.get("max_length")
            if min_len is not None and len(normalized) < int(min_len):
                raise ValueError(f"min_length {min_len}")
            if max_len is not None and len(normalized) > int(max_len):
                raise ValueError(f"max_length {max_len}")
            pattern = rule.get("pattern")
            if pattern and not re.fullmatch(str(pattern), normalized):
                raise ValueError(f"pattern {pattern}")
        elif field_type == "date":
            formats = list(rule.get("formats") or ["%Y-%m-%d"])
            normalized = _parse_date(value, formats)
        elif field_type == "money":
            amount = _parse_money(value)
            minimum = rule.get("min")
            if minimum is not None and amount < Decimal(str(minimum)):
                raise ValueError(f"min {minimum}")
            normalized = f"{amount:.2f}"
        elif field_type == "number":
            number = float(value)
            if rule.get("min") is not None and number < float(rule["min"]):
                raise ValueError(f"min {rule['min']}")
            if rule.get("max") is not None and number > float(rule["max"]):
                raise ValueError(f"max {rule['max']}")
            normalized = number
        elif field_type == "integer":
            number = int(value)
            if rule.get("min") is not None and number < int(rule["min"]):
                raise ValueError(f"min {rule['min']}")
            if rule.get("max") is not None and number > int(rule["max"]):
                raise ValueError(f"max {rule['max']}")
            normalized = number
        elif field_type == "boolean":
            normalized = _parse_bool(value)
        elif field_type == "enum":
            allowed = [str(item) for item in (rule.get("values") or [])]
            text = str(value).strip()
            if text not in allowed:
                raise ValueError(f"not in {allowed}")
            normalized = text
        else:
            raise ValueError(f"unsupported type {field_type}")
    except (ValueError, InvalidOperation, TypeError) as exc:
        anomalies.append(
            FieldAnomaly(name, "invalid_format", str(exc))
        )
        return None, anomalies, True

    # low confidence alone does not reject value, but blocks auto-valid
    return normalized, anomalies, False


def validate_document(
    document_type: str,
    fields: Mapping[str, Any],
    *,
    job_id: str | None = None,
    document_id: str | None = None,
    document_sha256: str | None = None,
    rules_path: Path = DEFAULT_RULES_PATH,
) -> ValidationResult:
    """Validate extracted fields against configurable doc_type rules."""
    if not isinstance(document_type, str) or not document_type.strip():
        raise ValidationRequestError("document_type is required")
    if not isinstance(fields, Mapping):
        raise ValidationRequestError("fields must be an object")

    rules = _load_rules(rules_path)
    types = rules["document_types"]
    if document_type not in types:
        known = ", ".join(sorted(types))
        raise ValidationRequestError(
            f"Unknown document_type {document_type!r}; known: {known}"
        )

    spec = types[document_type]
    field_rules = spec.get("fields") or {}
    required = [str(name) for name in (spec.get("required_fields") or [])]
    confidence_min = float(spec.get("confidence_min") or 0.0)
    validator_version = str(rules.get("validator_version") or "1.0")
    template_version = str(spec.get("template_version") or "1")

    missing = [name for name in required if name not in fields]
    anomalies: list[FieldAnomaly] = []
    rejected: list[str] = []
    normalized: dict[str, Any] = {}

    for name in missing:
        anomalies.append(
            FieldAnomaly(name, "missing_required", "Required field is missing")
        )

    for name, raw in fields.items():
        rule = field_rules.get(name)
        if rule is None:
            anomalies.append(
                FieldAnomaly(
                    name,
                    "unknown_field",
                    "Field is not defined for this document_type",
                )
            )
            rejected.append(name)
            continue
        value, field_anomalies, is_rejected = _check_field(
            name,
            rule,
            raw,
            confidence_min=confidence_min,
        )
        anomalies.extend(field_anomalies)
        if is_rejected:
            rejected.append(name)
        elif value is not None:
            normalized[name] = value

    # Optional configured fields present in rules but not required — skip if absent.
    for name, rule in field_rules.items():
        if name in fields or name in required:
            continue
        if rule.get("required"):
            missing.append(name)
            anomalies.append(
                FieldAnomaly(name, "missing_required", "Required field is missing")
            )

    blocking = [
        item
        for item in anomalies
        if item.code
        in {
            "missing_required",
            "invalid_format",
            "empty",
            "unknown_field",
        }
    ]
    soft = [item for item in anomalies if item.code == "low_confidence"]

    if blocking:
        status = STATUS_PENDING_REVIEW
    elif soft or missing:
        status = STATUS_PENDING_REVIEW
    elif len(normalized) < len(required):
        status = STATUS_PENDING_REVIEW
    else:
        # all required present and normalized
        if all(name in normalized for name in required):
            status = STATUS_VALID
        else:
            status = STATUS_PENDING_REVIEW

    return ValidationResult(
        document_type=document_type,
        status=status,
        fields=dict(fields),
        normalized_fields=normalized,
        missing_required_fields=sorted(set(missing)),
        anomalies=anomalies,
        rejected_fields=sorted(set(rejected)),
        template_version=template_version,
        validator_version=validator_version,
        job_id=job_id,
        document_id=document_id,
        document_sha256=document_sha256,
    )


def assert_downstream_ready(result: ValidationResult) -> None:
    """Raise if invalid payload must not leave the OCR contour."""
    if not result.is_valid:
        raise ValidationRequestError(
            "Validated status is not 'valid'; downstream export blocked "
            f"({len(result.anomalies)} anomalies, "
            f"missing={result.missing_required_fields})"
        )
