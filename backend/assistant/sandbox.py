"""Read-only SQL/code snippet for the chat. Nothing is sent to a database."""

from __future__ import annotations

import re

from django.http import HttpRequest

from audit.events import (
    ASSISTANT_SANDBOX_SNIPPET,
    CATEGORY_DATA_SECURITY,
    RESULT_FAILURE,
    RESULT_SUCCESS,
)
from assistant.sql_access import allowed_object_names
from audit.service import emit, request_context, subject_from_request

_WRITE = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|revoke|merge|exec|execute|copy|call)\b",
    re.IGNORECASE,
)
_RELATION = re.compile(
    r"\b(?:from|join)\s+([a-zA-Z_][\w]*)(?:\s*\.\s*([a-zA-Z_][\w]*))?",
    re.IGNORECASE,
)


class SandboxError(ValueError):
    """Snippet rejected by the read-only rule."""


def _relations(sql: str) -> list[str]:
    names: list[str] = []
    for match in _RELATION.finditer(sql):
        left, right = match.group(1), match.group(2)
        names.append(f"{left}.{right}".lower() if right else left.lower())
    return names


def _allowed(name: str, allowed: set[str]) -> bool:
    if name in allowed:
        return True
    return name.split(".")[-1] in allowed


def prepare_snippet(kind: str, text: str, *, request: HttpRequest) -> dict[str, str]:
    cleaned = (text or "").strip()
    if kind not in {"sql", "code"}:
        raise SandboxError("Неизвестный инструмент")
    if not cleaned:
        raise SandboxError("Введите текст")
    if len(cleaned) > 8000:
        raise SandboxError("Слишком длинный фрагмент")
    sql_body = cleaned.rstrip(";").strip()
    if kind == "sql" and (_WRITE.search(cleaned) or ";" in sql_body):
        emit(
            category=CATEGORY_DATA_SECURITY,
            event_type=ASSISTANT_SANDBOX_SNIPPET,
            result=RESULT_FAILURE,
            subject=subject_from_request(request),
            module="assistant",
            description="SQL snippet rejected: not read-only",
            request=request_context(request),
            details={"kind": "sql"},
        )
        raise SandboxError("Разрешён только текст запроса на чтение, без изменения данных")
    if kind == "sql":
        relations = _relations(sql_body)
        allowed = allowed_object_names()
        blocked = [name for name in relations if not _allowed(name, allowed)]
        if relations and not allowed:
            emit(
                category=CATEGORY_DATA_SECURITY,
                event_type=ASSISTANT_SANDBOX_SNIPPET,
                result=RESULT_FAILURE,
                subject=subject_from_request(request),
                module="assistant",
                description="SQL snippet rejected: access list is empty",
                request=request_context(request),
                details={"kind": "sql"},
            )
            raise SandboxError(
                "Список доступов пуст. Его задают в Центре настроек → Инструменты ассистента → SQL."
            )
        if blocked:
            emit(
                category=CATEGORY_DATA_SECURITY,
                event_type=ASSISTANT_SANDBOX_SNIPPET,
                result=RESULT_FAILURE,
                subject=subject_from_request(request),
                module="assistant",
                description="SQL snippet rejected: object is not in the access list",
                request=request_context(request),
                details={"kind": "sql", "objects": blocked},
            )
            raise SandboxError(
                f"Витрина «{blocked[0]}» не в списке доступов. "
                "Список настраивается в Центре настроек → Инструменты ассистента → SQL."
            )
    emit(
        category=CATEGORY_DATA_SECURITY,
        event_type=ASSISTANT_SANDBOX_SNIPPET,
        result=RESULT_SUCCESS,
        subject=subject_from_request(request),
        module="assistant",
        description="Sandbox snippet shown in chat, not executed",
        request=request_context(request),
        details={"kind": kind, "chars": len(cleaned)},
    )
    label = "SQL · только чтение" if kind == "sql" else "Код"
    return {"kind": kind, "label": label, "text": cleaned}
