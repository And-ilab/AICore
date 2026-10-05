from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from audit.events import (
    CATEGORY_ADMINISTRATION,
    CATEGORY_INTEGRATIONS,
    KB_SETTINGS_UPDATED,
    RESULT_FAILURE,
    RESULT_SUCCESS,
    SIEM_DELIVERY_FAILURE,
)
from audit.schema import (
    AuditEvent,
    AuditRequest,
    AuditSource,
    AuditSubject,
    build_event,
)
from audit.sinks.base import AuditSink
from audit.sinks.file import FileAuditSink
from audit.sinks.http import HttpAuditSink
from auth.roles import role_codes_for_user


logger = logging.getLogger(__name__)


def _configured_sink_names() -> tuple[str, ...]:
    configured = getattr(settings, "AUDIT_SINKS", ("file",))
    if isinstance(configured, str):
        names = tuple(
            name.strip().lower()
            for name in configured.split(",")
            if name.strip()
        )
    else:
        names = tuple(
            str(name).strip().lower()
            for name in configured
            if str(name).strip()
        )
    # Normalize alias: kuma → http (same HttpAuditSink / P2-05 JSON).
    normalized = tuple("http" if name == "kuma" else name for name in names)
    # INT-T-AUD-03 / §9.2.6: remote KUMA requires local file retention.
    if "http" in normalized and "file" not in normalized:
        logger.warning(
            "AUDIT_SINKS includes http/kuma without file; "
            "auto-enabling file fallback for local retention"
        )
        return ("file",) + normalized
    return normalized


def resolve_kuma_collector_url() -> str:
    """VI.3 prod KUMA HTTP collector URL (env)."""
    return (
        str(getattr(settings, "AUDIT_KUMA_COLLECTOR_URL", "") or "").strip()
        or str(getattr(settings, "AUDIT_HTTP_COLLECTOR_URL", "") or "").strip()
    )


def configured_sinks() -> tuple[AuditSink, ...]:
    sinks: list[AuditSink] = []
    collector_url = resolve_kuma_collector_url()
    for name in _configured_sink_names():
        if name == "file":
            sinks.append(FileAuditSink(settings.AUDIT_FILE_PATH))
        elif name == "http":
            if not collector_url:
                logger.error(
                    "KUMA/HTTP audit sink enabled without collector URL "
                    "(set AUDIT_KUMA_COLLECTOR_URL or AUDIT_HTTP_COLLECTOR_URL)"
                )
                continue
            sinks.append(
                HttpAuditSink(
                    collector_url,
                    settings.AUDIT_HTTP_TIMEOUT_SECONDS,
                )
            )
        else:
            logger.error("Unknown audit sink configured: %s", name)
    return tuple(sinks)


def request_context(request: HttpRequest) -> AuditRequest:
    request_id = getattr(request, "audit_request_id", None)
    if not request_id:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.audit_request_id = request_id
    return AuditRequest(
        request_id=request_id,
        method=request.method,
        path=request.path,
        client_ip=request.META.get("REMOTE_ADDR"),
    )


def subject_from_request(request: HttpRequest) -> AuditSubject:
    user = getattr(request, "user", None)
    authenticated = bool(getattr(user, "is_authenticated", False))
    username = user.get_username() if authenticated else "anonymous"
    return AuditSubject(
        user_login=username or "anonymous",
        roles=tuple(sorted(role_codes_for_user(user))),
    )


def emit(
    *,
    category: str,
    event_type: str,
    result: str,
    subject: AuditSubject,
    module: str,
    description: str,
    severity: str = "info",
    request: AuditRequest | None = None,
    outcome: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
    sinks: Iterable[AuditSink] | None = None,
) -> AuditEvent:
    event = build_event(
        category=category,
        event_type=event_type,
        result=result,
        subject=subject,
        source=AuditSource(
            service=settings.AUDIT_SOURCE_SERVICE,
            module=module,
        ),
        description=description,
        device_vendor=settings.AUDIT_DEVICE_VENDOR,
        device_product=settings.AUDIT_DEVICE_PRODUCT,
        device_version=settings.AUDIT_DEVICE_VERSION,
        severity=severity,
        request=request,
        outcome=outcome,
        details=details,
    )
    if not getattr(settings, "AUDIT_ENABLED", True):
        return event

    selected_sinks = tuple(sinks) if sinks is not None else configured_sinks()
    file_sinks = tuple(
        sink for sink in selected_sinks if isinstance(sink, FileAuditSink)
    )
    for sink in selected_sinks:
        try:
            sink.write(event)
        except Exception as exc:  # Sink failures must not break business flows.
            logger.error(
                "Audit sink %s failed: %s",
                type(sink).__name__,
                type(exc).__name__,
            )
            if isinstance(sink, HttpAuditSink):
                _record_http_failure(event, file_sinks, type(exc).__name__)
    return event


def _record_http_failure(
    original_event: AuditEvent,
    file_sinks: tuple[FileAuditSink, ...],
    error_type: str,
) -> None:
    if not file_sinks:
        return
    failure = build_event(
        category=CATEGORY_INTEGRATIONS,
        event_type=SIEM_DELIVERY_FAILURE,
        result=RESULT_FAILURE,
        subject=original_event.subject,
        source=AuditSource(
            service=settings.AUDIT_SOURCE_SERVICE,
            module="audit",
        ),
        description="KUMA HTTP delivery failed; event retained locally",
        device_vendor=settings.AUDIT_DEVICE_VENDOR,
        device_product=settings.AUDIT_DEVICE_PRODUCT,
        device_version=settings.AUDIT_DEVICE_VERSION,
        severity="high",
        request=original_event.request,
        details={
            "failed_event_id": original_event.EventID,
            "error_type": error_type,
        },
    )
    for sink in file_sinks:
        try:
            sink.write(failure)
        except Exception:
            logger.exception("Local audit fallback write failed")


def emit_kb_change(
    *,
    request: HttpRequest,
    profile: str,
    revision: int,
    changed_fields: Iterable[str],
) -> AuditEvent:
    return emit(
        category=CATEGORY_ADMINISTRATION,
        event_type=KB_SETTINGS_UPDATED,
        result=RESULT_SUCCESS,
        subject=subject_from_request(request),
        module="hub",
        description="ModelRegistry KB and LLM parameters updated",
        request=request_context(request),
        outcome={"revision": revision},
        details={
            "profile": profile,
            "changed_fields": sorted(set(changed_fields)),
        },
    )
