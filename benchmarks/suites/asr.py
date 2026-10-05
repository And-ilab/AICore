"""ASR benchmark suite entry point."""

from __future__ import annotations

from typing import Any

from benchmarks.suites.asr_streaming import run as run_streaming


def run() -> dict[str, Any]:
    return run_streaming()
