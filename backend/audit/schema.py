from __future__ import annotations

import socket
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

from audit.events import AUDIT_CATEGORIES, AUDIT_RESULTS


@dataclass(frozen=True)
class AuditSubject:
    user_login: str
    roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuditSource:
    service: str
    module: str
    host: str = field(default_factory=socket.gethostname)


@dataclass(frozen=True)
class AuditRequest:
    request_id: str
    method: str
    path: str
    client_ip: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    schema_version: str
    EventID: str
    Timestamp: str
    DeviceVendor: str
    DeviceProduct: str
    DeviceVersion: str
    category: str
    event_type: str
    result: str
    severity: str
    subject: AuditSubject
    source: AuditSource
    description: str
    request: AuditRequest | None = None
    outcome: Mapping[str, Any] = field(default_factory=dict)
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.category not in AUDIT_CATEGORIES:
            raise ValueError(f"Unknown VI.3 audit category: {self.category}")
        if self.result not in AUDIT_RESULTS:
            raise ValueError(f"Unknown audit result: {self.result}")
        if not self.event_type or not self.description:
            raise ValueError("event_type and description are required")
        if not self.subject.user_login:
            raise ValueError("subject.user_login is required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def build_event(
    *,
    category: str,
    event_type: str,
    result: str,
    subject: AuditSubject,
    source: AuditSource,
    description: str,
    device_vendor: str,
    device_product: str,
    device_version: str,
    severity: str = "info",
    request: AuditRequest | None = None,
    outcome: Mapping[str, Any] | None = None,
    details: Mapping[str, Any] | None = None,
) -> AuditEvent:
    return AuditEvent(
        schema_version="1.0",
        EventID=str(uuid.uuid4()),
        Timestamp=utc_timestamp(),
        DeviceVendor=device_vendor,
        DeviceProduct=device_product,
        DeviceVersion=device_version,
        category=category,
        event_type=event_type,
        result=result,
        severity=severity,
        subject=subject,
        source=source,
        description=description,
        request=request,
        outcome=dict(outcome or {}),
        details=dict(details or {}),
    )
