"""RPA whitelist and confirmed launch requests. No bank robot is called."""

from __future__ import annotations

import re
from typing import Any, Mapping

from hub.models import AssistantRpaRun, AssistantRpaScenario

CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")
NOT_CONNECTED = (
    "Сценарий в белом списке, запуск подтверждён. "
    "Платформа роботов банка ещё не подключена, в систему банка заход не выполнен."
)


class RpaError(ValueError):
    """Invalid scenario or a launch outside the whitelist."""


def serialize_scenario(row: AssistantRpaScenario) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "code": row.code,
        "description": row.description,
        "active": row.active,
    }


def list_scenarios(*, active_only: bool = False) -> list[dict[str, Any]]:
    rows = AssistantRpaScenario.objects.all()
    if active_only:
        rows = rows.filter(active=True)
    return [serialize_scenario(row) for row in rows]


def _clean(payload: Mapping[str, Any], *, partial: bool = False) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if not partial or "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise RpaError("Укажите название сценария")
        data["name"] = name[:200]
    if not partial or "code" in payload:
        code = str(payload.get("code") or "").strip().lower()
        if not CODE_RE.fullmatch(code):
            raise RpaError("Код: латиница, цифры и дефис, от 2 символов")
        data["code"] = code
    if not partial or "description" in payload:
        data["description"] = str(payload.get("description") or "").strip()[:2000]
    if not partial or "active" in payload:
        data["active"] = bool(payload.get("active", True))
    return data


def create_scenario(payload: Mapping[str, Any], *, username: str) -> dict[str, Any]:
    data = _clean(payload)
    if AssistantRpaScenario.objects.filter(code=data["code"]).exists():
        raise RpaError("Сценарий с таким кодом уже есть")
    row = AssistantRpaScenario.objects.create(updated_by=username, **data)
    return serialize_scenario(row)


def update_scenario(
    scenario_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    row = AssistantRpaScenario.objects.filter(pk=scenario_id).first()
    if row is None:
        raise RpaError("scenario not found")
    data = _clean(payload, partial=True)
    code = data.get("code")
    if code and AssistantRpaScenario.objects.exclude(pk=row.pk).filter(code=code).exists():
        raise RpaError("Сценарий с таким кодом уже есть")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_by = username
    row.save()
    return serialize_scenario(row)


def delete_scenario(scenario_id: int) -> None:
    row = AssistantRpaScenario.objects.filter(pk=scenario_id).first()
    if row is None:
        raise RpaError("scenario not found")
    if row.runs.exists():
        row.active = False
        row.save(update_fields=["active", "updated_at"])
        return
    row.delete()


def launch_scenario(
    scenario_id: int,
    *,
    username: str,
    confirm: bool,
) -> dict[str, Any]:
    if not confirm:
        raise RpaError("Запуск только после подтверждения")
    row = AssistantRpaScenario.objects.filter(pk=scenario_id).first()
    if row is None:
        raise RpaError("scenario not found")
    if not row.active:
        raise RpaError("Сценарий не в белом списке")
    run = AssistantRpaRun.objects.create(
        scenario=row,
        status=AssistantRpaRun.STATUS_CONFIRMED,
        detail=NOT_CONNECTED,
        requested_by=username,
    )
    return {
        "id": run.id,
        "scenario_id": row.id,
        "scenario_name": row.name,
        "scenario_code": row.code,
        "status": run.status,
        "status_label": "Подтверждено",
        "detail": run.detail,
    }
