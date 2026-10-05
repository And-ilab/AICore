from __future__ import annotations

import json
import threading
from pathlib import Path

from audit.schema import AuditEvent


class FileAuditSink:
    """Append-only UTF-8 JSONL sink for local retention."""

    _lock = threading.Lock()

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write(self, event: AuditEvent) -> None:
        payload = json.dumps(
            event.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.write("\n")
