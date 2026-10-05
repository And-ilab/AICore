"""Real-time operational panel for II.6 FR-RPT-CC-03 (online-chat)."""

from __future__ import annotations

from typing import Any

from reports.cc_chat_metrics import build_live_dashboard as _build


def build_live_dashboard() -> dict[str, Any]:
    return _build()
