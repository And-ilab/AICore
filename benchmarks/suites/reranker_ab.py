"""Optional A/B evaluation of baseline and cross-encoder QU rankings."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "qu_synonyms.json"
)
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from benchmarks.suites.qu_synonyms import load_dataset  # noqa: E402
from core.model_registry import (  # noqa: E402
    DEFAULT_REGISTRY_PATH,
    ModelRegistry,
)


REQUIREMENTS = ("FR-UND-06", "FR-UND-12")


class RerankerAbInputError(ValueError):
    """Raised when A/B ranking predictions are not comparable."""


def percentile(values: Sequence[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percent / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def load_rankings(
    path: Path,
    expected_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RerankerAbInputError(f"Rankings not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RerankerAbInputError(f"Invalid rankings JSON: {path}") from exc
    predictions = (
        payload.get("predictions")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(predictions, list):
        raise RerankerAbInputError(
            "Rankings JSON requires a 'predictions' list"
        )

    by_id: dict[str, Mapping[str, Any]] = {}
    for index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, Mapping):
            raise RerankerAbInputError(
                f"Prediction #{index} must be an object"
            )
        sample_id = prediction.get("id")
        matched = prediction.get("matched")
        rankings = prediction.get("ranked_results")
        latency_ms = prediction.get("latency_ms")
        if not isinstance(sample_id, str) or not sample_id:
            raise RerankerAbInputError(
                f"Prediction #{index} requires id"
            )
        if sample_id in by_id:
            raise RerankerAbInputError(
                f"Duplicate prediction id: {sample_id}"
            )
        if not isinstance(matched, bool):
            raise RerankerAbInputError(
                f"Prediction {sample_id!r} requires matched"
            )
        if not isinstance(rankings, list) or not 1 <= len(rankings) <= 5:
            raise RerankerAbInputError(
                f"Prediction {sample_id!r} requires 1..5 ranked results"
            )
        intent_ids: list[str] = []
        scores: list[float] = []
        for rank, result in enumerate(rankings, start=1):
            intent_id = (
                result.get("intent_id")
                if isinstance(result, Mapping)
                else None
            )
            score = (
                result.get("score")
                if isinstance(result, Mapping)
                else None
            )
            if not isinstance(intent_id, str) or not intent_id:
                raise RerankerAbInputError(
                    f"Prediction {sample_id!r} rank {rank} "
                    "requires intent_id"
                )
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not 0 <= score <= 1
            ):
                raise RerankerAbInputError(
                    f"Prediction {sample_id!r} rank {rank} "
                    "requires score in [0, 1]"
                )
            intent_ids.append(intent_id)
            scores.append(float(score))
        if len(intent_ids) != len(set(intent_ids)):
            raise RerankerAbInputError(
                f"Prediction {sample_id!r} has duplicate intent ids"
            )
        if scores != sorted(scores, reverse=True):
            raise RerankerAbInputError(
                f"Prediction {sample_id!r} scores must descend"
            )
        if (
            latency_ms is not None
            and (
                not isinstance(latency_ms, (int, float))
                or isinstance(latency_ms, bool)
                or latency_ms < 0
            )
        ):
            raise RerankerAbInputError(
                f"Prediction {sample_id!r} has invalid latency_ms"
            )
        by_id[sample_id] = prediction

    if set(by_id) != expected_ids:
        missing = sorted(expected_ids - set(by_id))
        unexpected = sorted(set(by_id) - expected_ids)
        raise RerankerAbInputError(
            "Ranking ids must exactly match dataset ids; "
            f"missing={missing}, unexpected={unexpected}"
        )
    return by_id


def evaluate_rankings(
    samples: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    positive_count = 0
    top1_count = 0
    recall_at_5_count = 0
    reciprocal_rank_total = 0.0
    ndcg_total = 0.0
    semantic_pass_count = 0
    latencies: list[float] = []

    for sample in samples:
        prediction = predictions[str(sample["id"])]
        ranked_ids = [
            result["intent_id"]
            for result in prediction["ranked_results"]
        ]
        expected_match = bool(sample["expected_match"])
        expected_intent = sample["expected_intent_id"]
        rank: int | None = None
        if expected_match:
            positive_count += 1
            if expected_intent in ranked_ids:
                rank = ranked_ids.index(expected_intent) + 1
                recall_at_5_count += 1
                reciprocal_rank_total += 1 / rank
                ndcg_total += 1 / math.log2(rank + 1)
            if rank == 1:
                top1_count += 1
            passed = prediction["matched"] and rank == 1
        else:
            passed = not prediction["matched"]
        semantic_pass_count += int(passed)
        latency = prediction.get("latency_ms")
        if latency is not None:
            latencies.append(float(latency))
        results.append(
            {
                "id": sample["id"],
                "category": sample["category"],
                "expected_match": expected_match,
                "expected_intent_id": expected_intent,
                "matched": prediction["matched"],
                "ranked_intent_ids": ranked_ids,
                "expected_rank": rank,
                "passed": passed,
                "latency_ms": latency,
            }
        )

    return {
        "sample_count": len(samples),
        "positive_count": positive_count,
        "semantic_pass_rate_percent": round(
            semantic_pass_count / len(samples) * 100,
            2,
        ),
        "top1_accuracy_percent": round(
            top1_count / positive_count * 100,
            2,
        ),
        "recall_at_5_percent": round(
            recall_at_5_count / positive_count * 100,
            2,
        ),
        "mrr": round(reciprocal_rank_total / positive_count, 4),
        "ndcg_at_5": round(ndcg_total / positive_count, 4),
        "latency_p50_ms": (
            round(percentile(latencies, 50), 2) if latencies else None
        ),
        "latency_p95_ms": (
            round(percentile(latencies, 95), 2) if latencies else None
        ),
        "latency_sample_count": len(latencies),
        "results": results,
    }


def compare(
    baseline: Mapping[str, Any],
    reranked: Mapping[str, Any],
) -> dict[str, Any]:
    metric_names = (
        "semantic_pass_rate_percent",
        "top1_accuracy_percent",
        "recall_at_5_percent",
        "mrr",
        "ndcg_at_5",
    )
    deltas = {
        metric: round(float(reranked[metric]) - float(baseline[metric]), 4)
        for metric in metric_names
    }
    baseline_latency = baseline["latency_p95_ms"]
    reranked_latency = reranked["latency_p95_ms"]
    latency_delta = (
        round(float(reranked_latency) - float(baseline_latency), 2)
        if baseline_latency is not None and reranked_latency is not None
        else None
    )
    no_quality_regression = all(
        deltas[metric] >= 0 for metric in metric_names
    )
    quality_improved = any(
        deltas[metric] > 0 for metric in metric_names
    )
    return {
        "deltas": deltas,
        "latency_p95_delta_ms": latency_delta,
        "no_quality_regression": no_quality_regression,
        "quality_improved": quality_improved,
        "recommendation": (
            "consider_reranker"
            if no_quality_regression and quality_improved
            else "skip_no_material_gain"
            if no_quality_regression
            else "reject_quality_regression"
        ),
    }


def run(
    *,
    baseline_path: Path | None = None,
    reranked_path: Path | None = None,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    model_override: str | None = None,
) -> dict[str, Any]:
    registry = ModelRegistry.load(registry_path)
    slot = registry.get_slot("reranker")
    model = model_override or slot.prod_candidate or slot.dev_model
    report = build_stub_report("qu", ("qu-cc-semantic-pairs",))
    report["report_id"] = report["report_id"].replace(
        "qu-",
        "reranker-ab-",
        1,
    )
    report["requirements"] = list(REQUIREMENTS)

    skip_reason: str | None = None
    if not model:
        skip_reason = "reranker_model_not_configured"
    elif baseline_path is None or reranked_path is None:
        skip_reason = "baseline_and_reranked_predictions_required"
    if skip_reason:
        report["runner_status"] = "stub"
        report["suite_details"] = {
            "test_type": "reranker_ab",
            "status": "skipped",
            "skip_reason": skip_reason,
            "blocking_for_p1_61": False,
            "configured_model": model,
            "registry_status": slot.status,
            "required_inputs": {
                "baseline": "QU rankings without cross-encoder",
                "reranked": "Same QU candidates after cross-encoder",
            },
        }
        return report

    samples = load_dataset(dataset_path)
    expected_ids = {str(sample["id"]) for sample in samples}
    baseline_predictions = load_rankings(baseline_path, expected_ids)
    reranked_predictions = load_rankings(reranked_path, expected_ids)
    baseline = evaluate_rankings(samples, baseline_predictions)
    reranked = evaluate_rankings(samples, reranked_predictions)
    comparison = compare(baseline, reranked)

    report["runner_status"] = "ready"
    report["metrics"]["accuracy_percent"] = {
        "value": reranked["top1_accuracy_percent"],
        "status": "measured",
    }
    report["metrics"]["latency_ms"] = {
        "p50": reranked["latency_p50_ms"] or 0.0,
        "p95": reranked["latency_p95_ms"] or 0.0,
        "status": (
            "measured"
            if reranked["latency_p95_ms"] is not None
            else "placeholder"
        ),
    }
    report["suite_details"] = {
        "test_type": "reranker_ab",
        "status": "measured",
        "blocking_for_p1_61": False,
        "configured_model": model,
        "registry_status": slot.status,
        "baseline": baseline,
        "reranked": reranked,
        "comparison": comparison,
        "selection_note": (
            "Optional reranking may be adopted only after on-prem, "
            "latency, license, and quality review."
        ),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Optionally compare QU ranking with a cross-encoder.",
    )
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--reranked", type=Path)
    parser.add_argument("--model", help="Pinned on-prem model override.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
    )
    return parser


def write_report(report: Mapping[str, Any], output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{report['report_id']}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(
        baseline_path=args.baseline,
        reranked_path=args.reranked,
        dataset_path=args.dataset,
        registry_path=args.registry,
        model_override=args.model,
    )
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
