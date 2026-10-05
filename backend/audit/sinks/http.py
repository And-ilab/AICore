from __future__ import annotations

import json
from urllib.request import Request, urlopen

from audit.schema import AuditEvent


class HttpAuditSink:
    """KUMA-compatible JSON HTTP collector sink (VI.3 / AUDIT_KUMA_COLLECTOR_URL).

    Posts the unchanged P2-05 ``AuditEvent`` JSON envelope; expects HTTP 2xx.
    """

    def __init__(self, url: str, timeout_seconds: float = 5.0) -> None:
        if not url:
            raise ValueError("Audit HTTP collector URL is required")
        self.url = url
        self.timeout_seconds = timeout_seconds

    def write(self, event: AuditEvent) -> None:
        body = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")
        request = Request(
            self.url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "User-Agent": "sufler-audit/1.0",
            },
        )
        with urlopen(request, timeout=self.timeout_seconds) as response:
            if not 200 <= response.status < 300:
                raise OSError(
                    f"Audit collector returned HTTP {response.status}"
                )
