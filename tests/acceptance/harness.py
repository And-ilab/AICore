"""P0-04 acceptance harness helpers (shared by test_{suf,chat,ass,doc,int}_t)."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from tests.acceptance.generate_matrix import render_markdown

ACCEPTANCE_DIR = Path(__file__).resolve().parent
MATRIX_JSON = ACCEPTANCE_DIR / "matrix.json"
MATRIX_MD = ACCEPTANCE_DIR / "matrix.md"

SMOKE_ID_RE = re.compile(r"-0[14]$")

MODULE_PREFIX = {
    "sufler": "SUF",
    "chat": "CHAT",
    "assistant": "ASS",
    "documents": "DOC",
    "integration": "INT",
}

_matrix_lock = threading.Lock()


def load_matrix() -> list[dict[str, str]]:
    return json.loads(MATRIX_JSON.read_text(encoding="utf-8"))


def save_matrix(cases: list[dict[str, str]]) -> None:
    MATRIX_JSON.write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MATRIX_MD.write_text(render_markdown(cases), encoding="utf-8")


def update_matrix_status(case_id: str, status: str) -> None:
    """Update one acceptance ID status in matrix.json / matrix.md."""
    if status not in {"pass", "fail", "pending", "skip"}:
        raise ValueError(f"unsupported matrix status: {status}")
    with _matrix_lock:
        cases = load_matrix()
        found = False
        for case in cases:
            if case["id"] == case_id:
                case["status"] = status
                found = True
                break
        if not found:
            raise KeyError(f"unknown acceptance id: {case_id}")
        save_matrix(cases)


def matrix_ids(*, module: str | None = None, prefix: str | None = None) -> list[str]:
    cases = load_matrix()
    ids = [case["id"] for case in cases]
    if module:
        ids = [
            case["id"]
            for case in cases
            if case["module"] == module
        ]
    if prefix:
        ids = [case_id for case_id in ids if case_id.startswith(prefix)]
    return ids


def is_smoke_id(case_id: str) -> bool:
    """Smoke subset: IDs ending in -01 or -04 (not -04a)."""
    return bool(SMOKE_ID_RE.search(case_id))


def smoke_ids_for(module: str) -> list[str]:
    return [case_id for case_id in matrix_ids(module=module) if is_smoke_id(case_id)]


def expand_ids_for(module: str) -> list[str]:
    return [
        case_id
        for case_id in matrix_ids(module=module)
        if not is_smoke_id(case_id)
    ]


def mark_acceptance(case_id: str):
    """Decorator: on success → matrix pass; on failure → fail."""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            try:
                result = fn(*args, **kwargs)
            except Exception:
                try:
                    update_matrix_status(case_id, "fail")
                except KeyError:
                    pass
                raise
            update_matrix_status(case_id, "pass")
            return result

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        wrapper.acceptance_id = case_id  # type: ignore[attr-defined]
        return wrapper

    return decorator
