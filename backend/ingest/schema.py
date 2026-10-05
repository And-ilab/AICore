from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


SUPPORTED_EVENT_TYPES = frozenset(
    {
        "article.version_published",
        "article.updated",
        "article.unpublished",
        "article.deleted",
    }
)
SUPPORTED_STATUSES = frozenset({"draft", "published", "archived"})
CHECKSUM_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class SuzPayloadError(ValueError):
    def __init__(self, fields: list[str]) -> None:
        self.fields = sorted(set(fields))
        super().__init__("Invalid SUZ webhook payload")


@dataclass(frozen=True)
class SuzPayload:
    event_id: uuid.UUID
    event_type: str
    occurred_at: datetime
    article_id: int
    iblock_id: int
    section_id: int | None
    version_id: int | None
    version_number: int | None
    is_current: bool | None
    status: str | None
    title: str
    preview: str
    body_html: str
    body_plain: str
    permalink: str
    locale: str
    visibility_scope: tuple[str, ...]
    checksum: str
    changed_fields: tuple[str, ...]

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> SuzPayload:
        errors: list[str] = []

        try:
            event_id = uuid.UUID(str(data.get("event_id", "")))
        except ValueError:
            errors.append("event_id")
            event_id = uuid.UUID(int=0)
        event_type = data.get("event_type")
        if event_type not in SUPPORTED_EVENT_TYPES:
            errors.append("event_type")
            event_type = str(event_type or "")
        try:
            occurred_at = datetime.fromisoformat(
                str(data.get("occurred_at", "")).replace("Z", "+00:00")
            )
            if occurred_at.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append("occurred_at")
            occurred_at = datetime.min

        article_id = _positive_int(data, "article_id", errors)
        iblock_id = _positive_int(data, "iblock_id", errors)
        section_id = _optional_int(data, "section_id", errors)
        version_id = _optional_int(data, "version_id", errors)
        version_number = _optional_int(data, "version_number", errors)
        is_current = data.get("is_current")
        if is_current is not None and not isinstance(is_current, bool):
            errors.append("is_current")
            is_current = None

        status = data.get("status")
        if event_type != "article.deleted" and status not in SUPPORTED_STATUSES:
            errors.append("status")
        if status is not None:
            status = str(status)

        title = _string(data, "title")
        preview = _string(data, "preview")
        body_html = _string(data, "body_html")
        body_plain = _string(data, "body_plain")
        permalink = _string(data, "permalink")
        locale = _string(data, "locale")
        checksum = _string(data, "checksum")
        visibility_scope = (
            _string_tuple(
                data.get("visibility_scope"),
                "visibility_scope",
                errors,
            )
            if "visibility_scope" in data
            else ()
        )
        changed_fields = _string_tuple(
            data.get("changed_fields", []),
            "changed_fields",
            errors,
        )

        if event_type == "article.version_published":
            for field_name, value in (
                ("version_id", version_id),
                ("version_number", version_number),
                ("is_current", is_current),
                ("title", title),
                ("body_plain", body_plain),
                ("permalink", permalink),
                ("locale", locale),
            ):
                if value in {None, ""}:
                    errors.append(field_name)
            if status != "published":
                errors.append("status")
            if is_current is not True:
                errors.append("is_current")
            if not visibility_scope:
                errors.append("visibility_scope")
            if not CHECKSUM_PATTERN.fullmatch(checksum):
                errors.append("checksum")
        elif event_type == "article.updated" and status != "draft":
            errors.append("status")
        elif event_type == "article.unpublished" and status != "archived":
            errors.append("status")

        if errors:
            raise SuzPayloadError(errors)
        return cls(
            event_id=event_id,
            event_type=event_type,
            occurred_at=occurred_at,
            article_id=article_id,
            iblock_id=iblock_id,
            section_id=section_id,
            version_id=version_id,
            version_number=version_number,
            is_current=is_current,
            status=status,
            title=title,
            preview=preview,
            body_html=body_html,
            body_plain=body_plain,
            permalink=permalink,
            locale=locale,
            visibility_scope=visibility_scope,
            checksum=checksum,
            changed_fields=changed_fields,
        )


def _positive_int(
    data: Mapping[str, Any],
    field: str,
    errors: list[str],
) -> int:
    value = data.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(field)
        return 0
    return value


def _optional_int(
    data: Mapping[str, Any],
    field: str,
    errors: list[str],
) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        errors.append(field)
        return None
    return value


def _string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def _string_tuple(
    value: Any,
    field: str,
    errors: list[str],
) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        errors.append(field)
        return ()
    return tuple(item.strip() for item in value)
