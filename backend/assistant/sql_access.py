"""Configurable read-only SQL access list. No bank database is queried."""

from __future__ import annotations

import re
from typing import Any, Mapping

from hub.models import AssistantSqlAccess

OBJECT_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}(?:\.[a-z][a-z0-9_]{1,40})?$")


class SqlAccessError(ValueError):
    """Invalid access row."""


def serialize_access(row: AssistantSqlAccess) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "object_name": row.object_name,
        "description": row.description,
        "active": row.active,
    }


def list_accesses(*, active_only: bool = False) -> list[dict[str, Any]]:
    rows = AssistantSqlAccess.objects.all()
    if active_only:
        rows = rows.filter(active=True)
    return [serialize_access(row) for row in rows]


def allowed_object_names() -> set[str]:
    return set(
        AssistantSqlAccess.objects.filter(active=True).values_list("object_name", flat=True)
    )


def _clean(payload: Mapping[str, Any], *, partial: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise SqlAccessError("Укажите название доступа")
        data["name"] = name[:200]
    if not partial or "object_name" in payload:
        object_name = str(payload.get("object_name") or "").strip().lower()
        if not OBJECT_RE.fullmatch(object_name):
            raise SqlAccessError(
                "Витрина: латиница, цифры и подчёркивание, например cards"
            )
        data["object_name"] = object_name
    if not partial or "description" in payload:
        data["description"] = str(payload.get("description") or "").strip()[:2000]
    if not partial or "active" in payload:
        data["active"] = bool(payload.get("active", True))
    return data


def create_access(payload: Mapping[str, Any], *, username: str) -> dict[str, Any]:
    data = _clean(payload)
    if AssistantSqlAccess.objects.filter(object_name=data["object_name"]).exists():
        raise SqlAccessError("Такая витрина уже есть в списке")
    row = AssistantSqlAccess.objects.create(updated_by=username, **data)
    return serialize_access(row)


def update_access(
    access_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    row = AssistantSqlAccess.objects.filter(pk=access_id).first()
    if row is None:
        raise SqlAccessError("access not found")
    data = _clean(payload, partial=True)
    object_name = data.get("object_name")
    if (
        object_name
        and AssistantSqlAccess.objects.exclude(pk=row.pk).filter(object_name=object_name).exists()
    ):
        raise SqlAccessError("Такая витрина уже есть в списке")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by = username
    row.save()
    return serialize_access(row)


def delete_access(access_id: int) -> None:
    row = AssistantSqlAccess.objects.filter(pk=access_id).first()
    if row is None:
        raise SqlAccessError("access not found")
    row.delete()
