"""OCR benchmark suite entry point."""

from __future__ import annotations

from typing import Any

from benchmarks.suites.ocr_extraction import run as run_extraction


def run() -> dict[str, Any]:
    return run_extraction()
