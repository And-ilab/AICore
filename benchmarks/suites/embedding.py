"""Embedding benchmark suite entry point."""

from __future__ import annotations

from typing import Any

from benchmarks.suites.embedding_recall import run as run_recall


def run() -> dict[str, Any]:
    return run_recall()
