"""LLM benchmark suite entry point."""

from __future__ import annotations

from typing import Any

from benchmarks.suites.llm_sufler_cc import run as run_sufler_cc


def run() -> dict[str, Any]:
    return run_sufler_cc()
