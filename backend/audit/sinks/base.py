from __future__ import annotations

from typing import Protocol

from audit.schema import AuditEvent


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> None:
        """Persist or deliver one structured event."""
