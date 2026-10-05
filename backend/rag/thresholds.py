"""Validated retrieval thresholds backed by ModelRegistry.

FR-LLM-04 defines one threshold for including a fragment in RAG context and
another, stricter threshold for returning a deterministic answer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from core.model_registry import DEFAULT_REGISTRY_PATH, ModelRegistry


CONTEXT_INCLUSION = "context_inclusion"
DETERMINISTIC_ANSWER = "deterministic_answer"
SUPPORTED_THRESHOLDS = frozenset(
    {CONTEXT_INCLUSION, DETERMINISTIC_ANSWER}
)


class RetrievalThresholdError(ValueError):
    """Raised when retrieval thresholds are absent or unsafe."""


def _validate_score(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RetrievalThresholdError(
            f"{name} must be a number between 0 and 1"
        )
    numeric = float(value)
    if not 0 <= numeric <= 1:
        raise RetrievalThresholdError(
            f"{name} must be between 0 and 1"
        )
    return numeric


@dataclass(frozen=True)
class RetrievalThresholds:
    context_inclusion: float
    deterministic_answer: float
    status: str = "provisional"

    def __post_init__(self) -> None:
        context = _validate_score(
            CONTEXT_INCLUSION,
            self.context_inclusion,
        )
        deterministic = _validate_score(
            DETERMINISTIC_ANSWER,
            self.deterministic_answer,
        )
        if context > deterministic:
            raise RetrievalThresholdError(
                "context_inclusion cannot exceed deterministic_answer"
            )
        if not isinstance(self.status, str) or not self.status.strip():
            raise RetrievalThresholdError("status must be a non-empty string")
        object.__setattr__(self, "context_inclusion", context)
        object.__setattr__(self, "deterministic_answer", deterministic)

    def get(self, name: str) -> float:
        if name == CONTEXT_INCLUSION:
            return self.context_inclusion
        if name == DETERMINISTIC_ANSWER:
            return self.deterministic_answer
        raise KeyError(f"Unknown retrieval threshold: {name}")


def get_thresholds(
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> RetrievalThresholds:
    registry = ModelRegistry.load(registry_path)
    kpi = registry.get_slot("embedding").kpi
    try:
        context = kpi["context_inclusion_threshold"]
        deterministic = kpi["deterministic_answer_threshold"]
        status = kpi["retrieval_threshold_status"]
    except KeyError as exc:
        raise RetrievalThresholdError(
            f"ModelRegistry is missing retrieval field: {exc.args[0]}"
        ) from exc
    return RetrievalThresholds(
        context_inclusion=context,
        deterministic_answer=deterministic,
        status=status,
    )


def get_threshold(
    name: str,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> float:
    return get_thresholds(registry_path).get(name)


def _replace_registry_value(
    content: str,
    key: str,
    value: str,
) -> str:
    pattern = rf"(?m)^(\s+{re.escape(key)}:\s*).*$"
    updated, count = re.subn(
        pattern,
        rf"\g<1>{value}",
        content,
        count=1,
    )
    if count != 1:
        raise RetrievalThresholdError(
            f"ModelRegistry field not found: {key}"
        )
    return updated


def set_thresholds(
    context_inclusion: float,
    deterministic_answer: float,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    status: str = "dev_frozen",
    benchmark_report: str | None = None,
    sign_off: str | None = None,
) -> RetrievalThresholds:
    thresholds = RetrievalThresholds(
        context_inclusion=context_inclusion,
        deterministic_answer=deterministic_answer,
        status=status,
    )
    path = Path(registry_path)
    registry = ModelRegistry.load(path)
    profile = registry.get_profile("kb_cc_production")
    if profile.status == "dev_frozen":
        if not benchmark_report or not benchmark_report.strip():
            raise RetrievalThresholdError(
                "Frozen thresholds require a benchmark_report"
            )
        if not sign_off or not sign_off.strip():
            raise RetrievalThresholdError(
                "Frozen thresholds require sign_off"
            )
        if status != "dev_frozen":
            raise RetrievalThresholdError(
                "A calibrated baseline must be re-frozen as dev_frozen"
            )
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RetrievalThresholdError(
            f"ModelRegistry not found: {path}"
        ) from exc

    updated = _replace_registry_value(
        content,
        "context_inclusion_threshold",
        f"{thresholds.context_inclusion:.4f}",
    )
    updated = _replace_registry_value(
        updated,
        "deterministic_answer_threshold",
        f"{thresholds.deterministic_answer:.4f}",
    )
    updated = _replace_registry_value(
        updated,
        "retrieval_threshold_status",
        thresholds.status,
    )
    updated = _replace_registry_value(
        updated,
        "context_inclusion",
        f"{thresholds.context_inclusion:.4f}",
    )
    updated = _replace_registry_value(
        updated,
        "deterministic_answer",
        f"{thresholds.deterministic_answer:.4f}",
    )
    updated = _replace_registry_value(
        updated,
        "selection_basis",
        "measured_benchmark",
    )
    updated = _replace_registry_value(
        updated,
        "p1_22_threshold_report",
        json.dumps(benchmark_report, ensure_ascii=False),
    )
    updated = _replace_registry_value(
        updated,
        "last_sign_off",
        json.dumps(sign_off, ensure_ascii=False),
    )
    path.write_text(updated, encoding="utf-8")

    loaded = get_thresholds(path)
    if loaded != thresholds:
        raise RetrievalThresholdError(
            "ModelRegistry verification failed after threshold update"
        )
    return loaded


def set_threshold(
    name: str,
    value: float,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    *,
    status: str = "dev_frozen",
    benchmark_report: str | None = None,
    sign_off: str | None = None,
) -> RetrievalThresholds:
    if name not in SUPPORTED_THRESHOLDS:
        raise KeyError(f"Unknown retrieval threshold: {name}")
    current = get_thresholds(registry_path)
    context = (
        value
        if name == CONTEXT_INCLUSION
        else current.context_inclusion
    )
    deterministic = (
        value
        if name == DETERMINISTIC_ANSWER
        else current.deterministic_answer
    )
    return set_thresholds(
        context,
        deterministic,
        registry_path,
        status=status,
        benchmark_report=benchmark_report,
        sign_off=sign_off,
    )
