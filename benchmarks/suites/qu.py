"""Query-understanding benchmark suite entry point."""

from __future__ import annotations

from typing import Any

from benchmarks.suites.qu_synonyms import run as run_synonyms


def run() -> dict[str, Any]:
    return run_synonyms()
