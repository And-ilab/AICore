"""Shared report builder for benchmark suite stubs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence


REPORT_SCHEMA_VERSION = "1.0"


def build_stub_report(
    suite: str,
    datasets: Sequence[str],
) -> dict[str, Any]:
    """Return the stable report shape until a real model runner is wired."""
    generated_at = datetime.now(timezone.utc)
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": (
            f"{suite}-{generated_at.strftime('%Y%m%dT%H%M%S%fZ')}"
        ),
        "suite": suite,
        "runner_status": "stub",
        "generated_at": generated_at.isoformat(),
        "datasets": list(datasets),
        "metrics": {
            "latency_ms": {
                "p50": 0.0,
                "p95": 0.0,
                "status": "placeholder",
            },
            "accuracy_percent": {
                "value": None,
                "status": "placeholder",
            },
        },
    }
