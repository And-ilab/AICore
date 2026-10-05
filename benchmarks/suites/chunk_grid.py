"""Chunk-size/overlap calibration grid for FR-LLM-03."""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import product
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from core.model_registry import ModelRegistry  # noqa: E402


DEFAULT_REGISTRY_PATH = (
    REPOSITORY_ROOT / "backend" / "config" / "model_registry.yaml"
)
CHUNK_SIZES = (256, 512, 1024)
CHUNK_OVERLAPS = (50, 100, 200)
TOP_K = 5
REQUIREMENT = "FR-LLM-03"
CALIBRATION_PROFILE = "kb_cc_production"


class ChunkGridInputError(ValueError):
    """Raised when measured grid scores are incomplete or malformed."""


def expected_combinations() -> set[tuple[int, int]]:
    return set(product(CHUNK_SIZES, CHUNK_OVERLAPS))


def load_scores(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ChunkGridInputError(f"Scores not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ChunkGridInputError(f"Invalid scores JSON: {path}") from exc

    scores = payload.get("scores") if isinstance(payload, Mapping) else None
    if not isinstance(scores, list):
        raise ChunkGridInputError("Scores JSON must contain a 'scores' list")

    parsed: list[dict[str, Any]] = []
    combinations: set[tuple[int, int]] = set()
    for index, score in enumerate(scores, start=1):
        if not isinstance(score, Mapping):
            raise ChunkGridInputError(f"Score #{index} must be an object")
        chunk_size = score.get("chunk_size_tokens")
        overlap = score.get("overlap_tokens")
        recall = score.get("recall_at_5_percent")
        if (
            not isinstance(chunk_size, int)
            or isinstance(chunk_size, bool)
            or not isinstance(overlap, int)
            or isinstance(overlap, bool)
        ):
            raise ChunkGridInputError(
                f"Score #{index} has invalid chunk parameters"
            )
        if (
            not isinstance(recall, (int, float))
            or isinstance(recall, bool)
            or not 0 <= recall <= 100
        ):
            raise ChunkGridInputError(
                f"Score #{index} has invalid recall@5"
            )
        combination = (chunk_size, overlap)
        if combination in combinations:
            raise ChunkGridInputError(
                f"Duplicate grid combination: {combination}"
            )
        combinations.add(combination)
        parsed.append(
            {
                "chunk_size_tokens": chunk_size,
                "overlap_tokens": overlap,
                "recall_at_5_percent": float(recall),
                "status": "measured",
            }
        )

    missing = expected_combinations() - combinations
    extra = combinations - expected_combinations()
    if missing or extra:
        raise ChunkGridInputError(
            "Scores must cover exactly the configured 3x3 grid; "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    return parsed


def select_best(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Select highest recall; ties prefer fewer/larger chunks."""
    if not scores:
        raise ChunkGridInputError("Cannot select best from empty scores")
    best = max(
        scores,
        key=lambda score: (
            float(score["recall_at_5_percent"]),
            int(score["chunk_size_tokens"]),
            -int(score["overlap_tokens"]),
        ),
    )
    return dict(best)


def placeholder_grid() -> list[dict[str, Any]]:
    return [
        {
            "chunk_size_tokens": chunk_size,
            "overlap_tokens": overlap,
            "recall_at_5_percent": None,
            "status": "placeholder",
        }
        for chunk_size, overlap in product(CHUNK_SIZES, CHUNK_OVERLAPS)
    ]


def run(scores_path: Path | None = None) -> dict[str, Any]:
    measured = scores_path is not None
    grid = load_scores(scores_path) if scores_path else placeholder_grid()
    best = select_best(grid) if measured else None
    report = build_stub_report("embedding", ("embedding-suz-recall",))
    report["report_id"] = report["report_id"].replace(
        "embedding-",
        "chunk-grid-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["accuracy_percent"] = {
        "value": best["recall_at_5_percent"] if best else None,
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "chunk_grid",
        "metric": "recall@5",
        "top_k": TOP_K,
        "calibration_profile": CALIBRATION_PROFILE,
        "target_index": "cc_production",
        "grid": grid,
        "best_combination": best,
        "selection_rule": (
            "highest recall@5; ties prefer larger chunk size and "
            "smaller overlap to reduce index size"
        ),
        "registry_written": False,
    }
    return report


def write_optimal_defaults(
    registry_path: Path,
    best: Mapping[str, Any],
    *,
    benchmark_report: str,
    sign_off: str,
) -> None:
    """Update only calibration values while preserving YAML comments."""
    if not benchmark_report.strip():
        raise ChunkGridInputError("benchmark_report is required")
    if not sign_off.strip():
        raise ChunkGridInputError("sign_off is required")
    try:
        content = registry_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ChunkGridInputError(
            f"Model registry not found: {registry_path}"
        ) from exc

    replacements = {
        "optimal_chunk_size_tokens": str(best["chunk_size_tokens"]),
        "optimal_chunk_overlap_tokens": str(best["overlap_tokens"]),
        "chunk_selection_status": "dev_frozen",
        "chunk_size_tokens": str(best["chunk_size_tokens"]),
        "chunk_overlap_tokens": str(best["overlap_tokens"]),
        "selection_basis": "measured_benchmark",
        "p1_21_chunk_grid_report": json.dumps(
            benchmark_report,
            ensure_ascii=False,
        ),
        "last_sign_off": json.dumps(sign_off, ensure_ascii=False),
    }
    updated = content
    for key, value in replacements.items():
        pattern = rf"(?m)^(\s+{re.escape(key)}:\s*).*$"
        updated, count = re.subn(
            pattern,
            rf"\g<1>{value}",
            updated,
            count=1,
        )
        if count != 1:
            raise ChunkGridInputError(
                f"Registry calibration field not found: {key}"
            )
    registry_path.write_text(updated, encoding="utf-8")
    profile = ModelRegistry.load(registry_path).get_profile(
        "kb_cc_production"
    )
    if (
        profile.chunk_size_tokens != best["chunk_size_tokens"]
        or profile.chunk_overlap_tokens != best["overlap_tokens"]
    ):
        raise ChunkGridInputError(
            "ModelRegistry verification failed after chunk update"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate FR-LLM-03 chunk size and overlap.",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        help="Measured JSON covering all nine grid combinations.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
    )
    parser.add_argument(
        "--write-registry",
        action="store_true",
        help="Write measured best combination to ModelRegistry.",
    )
    parser.add_argument(
        "--sign-off",
        help="Approver/change-ticket reference required for frozen config.",
    )
    return parser


def write_report(report: Mapping[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / f"{report['report_id']}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args.scores)
    if args.write_registry:
        best = report["suite_details"]["best_combination"]
        if best is None:
            print(
                "Registry was not changed: --write-registry requires "
                "measured --scores.",
                file=sys.stderr,
            )
            return 2
        if not args.sign_off:
            print(
                "Registry was not changed: --sign-off is required.",
                file=sys.stderr,
            )
            return 2
        expected_report_path = (
            args.output / f"{report['report_id']}.json"
        )
        write_optimal_defaults(
            args.registry,
            best,
            benchmark_report=str(expected_report_path),
            sign_off=args.sign_off,
        )
        report["suite_details"]["registry_written"] = True
        report["suite_details"]["registry_path"] = str(args.registry)

    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
