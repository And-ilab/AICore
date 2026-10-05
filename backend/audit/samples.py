"""INT-T-AUD sample events (VI.3 / §9.3) — P2-05 schema_version=1.0 unchanged."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.conf import settings

from audit.events import (
    ACCESS_DENIED,
    CATEGORY_ADMINISTRATION,
    CATEGORY_AUTHENTICATION,
    CATEGORY_AUTHORIZATION,
    CATEGORY_INTEGRATIONS,
    KB_SETTINGS_UPDATED,
    LOGIN_FAILURE,
    LOGIN_SUCCESS,
    LOGOUT,
    RESULT_FAILURE,
    RESULT_SUCCESS,
    SIEM_DELIVERY_FAILURE,
)
from audit.schema import AuditEvent, AuditRequest, AuditSubject
from audit.service import emit
from audit.sinks.base import AuditSink


# Canonical sample set for INT-T-AUD-01…03 smoke against KUMA collector.
INT_T_AUD_SAMPLE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "id": "INT-T-AUD-01.login_success",
        "category": CATEGORY_AUTHENTICATION,
        "event_type": LOGIN_SUCCESS,
        "result": RESULT_SUCCESS,
        "description": "INT-T-AUD sample: AD login success",
        "subject": AuditSubject(
            user_login="int_t_aud.operator",
            roles=("contact_center_telephony_operator",),
        ),
        "module": "auth",
        "severity": "info",
    },
    {
        "id": "INT-T-AUD-01.login_failure",
        "category": CATEGORY_AUTHENTICATION,
        "event_type": LOGIN_FAILURE,
        "result": RESULT_FAILURE,
        "description": "INT-T-AUD sample: AD login failure",
        "subject": AuditSubject(user_login="int_t_aud.unknown"),
        "module": "auth",
        "severity": "warning",
    },
    {
        "id": "INT-T-AUD-01.logout",
        "category": CATEGORY_AUTHENTICATION,
        "event_type": LOGOUT,
        "result": RESULT_SUCCESS,
        "description": "INT-T-AUD sample: logout",
        "subject": AuditSubject(
            user_login="int_t_aud.operator",
            roles=("contact_center_telephony_operator",),
        ),
        "module": "auth",
        "severity": "info",
    },
    {
        "id": "INT-T-AUD-02.access_denied",
        "category": CATEGORY_AUTHORIZATION,
        "event_type": ACCESS_DENIED,
        "result": RESULT_FAILURE,
        "description": "INT-T-AUD sample: access denied",
        "subject": AuditSubject(user_login="int_t_aud.operator"),
        "module": "rbac",
        "severity": "warning",
        "outcome": {"http_status": 403},
        "request": AuditRequest(
            request_id="int-t-aud-access-denied",
            method="GET",
            path="/api/admin/protected/",
            client_ip="127.0.0.1",
        ),
    },
    {
        "id": "INT-T-AUD-01.kb_settings",
        "category": CATEGORY_ADMINISTRATION,
        "event_type": KB_SETTINGS_UPDATED,
        "result": RESULT_SUCCESS,
        "description": "INT-T-AUD sample: KB settings updated",
        "subject": AuditSubject(
            user_login="int_t_aud.admin",
            roles=("software_administrator",),
        ),
        "module": "hub",
        "severity": "info",
        "details": {"profile": "default", "changed_fields": ["llm_model"]},
    },
)


def emit_int_t_aud_samples(
    *,
    sinks: Iterable[AuditSink] | None = None,
    include_delivery_failure_probe: bool = False,
) -> list[AuditEvent]:
    """Emit INT-T-AUD sample events through configured (or injected) sinks.

    Does not alter P2-05 envelope (``schema_version=1.0`` via ``build_event``).
    """
    emitted: list[AuditEvent] = []
    selected = tuple(sinks) if sinks is not None else None
    for spec in INT_T_AUD_SAMPLE_SPECS:
        event = emit(
            category=spec["category"],
            event_type=spec["event_type"],
            result=spec["result"],
            subject=spec["subject"],
            module=spec["module"],
            description=spec["description"],
            severity=spec.get("severity", "info"),
            request=spec.get("request"),
            outcome=spec.get("outcome"),
            details={
                "int_t_aud_id": spec["id"],
                **dict(spec.get("details") or {}),
            },
            sinks=selected,
        )
        emitted.append(event)

    if include_delivery_failure_probe:
        # INT-T-AUD-03 signalling taxonomy (local-only probe; not sent as success).
        emitted.append(
            emit(
                category=CATEGORY_INTEGRATIONS,
                event_type=SIEM_DELIVERY_FAILURE,
                result=RESULT_FAILURE,
                subject=AuditSubject(user_login="system"),
                module="audit",
                description=(
                    "INT-T-AUD sample probe: SIEM delivery failure taxonomy"
                ),
                severity="high",
                details={
                    "int_t_aud_id": "INT-T-AUD-03.siem_delivery_failure",
                    "probe": True,
                    "collector": getattr(
                        settings,
                        "AUDIT_KUMA_COLLECTOR_URL",
                        "",
                    )
                    or getattr(settings, "AUDIT_HTTP_COLLECTOR_URL", ""),
                },
                sinks=selected,
            )
        )
    return emitted
