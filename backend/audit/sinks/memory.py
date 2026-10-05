from __future__ import annotations

from audit.schema import AuditEvent


class MemoryAuditSink:
    """Deterministic sink for unit tests and local mocks."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: AuditEvent) -> None:
        self.events.append(event.to_dict())
