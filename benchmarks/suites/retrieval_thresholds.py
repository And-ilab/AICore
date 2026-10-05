"""Calibrate FR-LLM-04 retrieval thresholds from labeled similarity scores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from core.model_registry import DEFAULT_REGISTRY_PATH  # noqa: E402
from rag.thresholds import get_thresholds, set_thresholds  # noqa: E402


REQUIREMENT = "FR-LLM-04"


class ThresholdCalibrationError(ValueError):
    """Raised when labeled scores cannot produce safe thresholds."""


def load_labeled_scores(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ThresholdCalibrationError(
            f"Calibration samples not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ThresholdCalibrationError(
            f"Invalid calibration JSON: {path}"
        ) from exc

    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or not samples:
        raise ThresholdCalibrationError(
            "Calibration JSON requires a non-empty 'samples' list"
        )

    parsed: list[dict[str, Any]] = []
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise ThresholdCalibrationError(
                f"Sample #{index} must be an object"
            )
        score = sample.get("score")
        relevant = sample.get("relevant")
        deterministic_correct = sample.get("deterministic_correct")
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= score <= 1
        ):
            raise ThresholdCalibrationError(
                f"Sample #{index} has an invalid score"
            )
        if not isinstance(relevant, bool):
            raise ThresholdCalibrationError(
                f"Sample #{index} requires boolean relevant"
            )
        if not isinstance(deterministic_correct, bool):
            raise ThresholdCalibrationError(
                f"Sample #{index} requires boolean deterministic_correct"
            )
        if deterministic_correct and not relevant:
            raise ThresholdCalibrationError(
                f"Sample #{index} cannot be deterministic_correct "
                "when it is not relevant"
            )
        parsed.append(
            {
                "id": str(sample.get("id", f"sample-{index}")),
                "score": float(score),
                "relevant": relevant,
                "deterministic_correct": deterministic_correct,
            }
        )
    return parsed


def classification_metrics(
    samples: Sequence[Mapping[str, Any]],
    threshold: float,
    label: str,
) -> dict[str, Any]:
    predicted = [sample["score"] >= threshold for sample in samples]
    actual = [bool(sample[label]) for sample in samples]
    true_positive = sum(
        prediction and expected
        for prediction, expected in zip(predicted, actual)
    )
    false_positive = sum(
        prediction and not expected
        for prediction, expected in zip(predicted, actual)
    )
    false_negative = sum(
        not prediction and expected
        for prediction, expected in zip(predicted, actual)
    )
    predicted_positive = true_positive + false_positive
    precision = (
        true_positive / predicted_positive
        if predicted_positive
        else 0.0
    )
    recall = (
        true_positive / (true_positive + false_negative)
        if true_positive + false_negative
        else 0.0
    )
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0
    )
    return {
        "threshold": threshold,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "predicted_positive": predicted_positive,
    }


def calibrate(
    samples: Sequence[Mapping[str, Any]],
    *,
    deterministic_precision_min: float = 0.98,
) -> dict[str, Any]:
    if not 0 < deterministic_precision_min <= 1:
        raise ThresholdCalibrationError(
            "deterministic_precision_min must be in (0, 1]"
        )
    candidates = sorted({0.0, 1.0, *(sample["score"] for sample in samples)})
    context_metrics = [
        classification_metrics(samples, threshold, "relevant")
        for threshold in candidates
    ]
    context_best = max(
        context_metrics,
        key=lambda metric: (
            metric["f1"],
            metric["recall"],
            metric["precision"],
            metric["threshold"],
        ),
    )

    deterministic_metrics = [
        classification_metrics(
            samples,
            threshold,
            "deterministic_correct",
        )
        for threshold in candidates
        if threshold >= context_best["threshold"]
    ]
    safe_deterministic = [
        metric
        for metric in deterministic_metrics
        if metric["predicted_positive"] > 0
        and metric["precision"] >= deterministic_precision_min
    ]
    if not safe_deterministic:
        raise ThresholdCalibrationError(
            "No deterministic threshold reaches the required precision"
        )
    deterministic_best = max(
        safe_deterministic,
        key=lambda metric: (
            metric["recall"],
            metric["precision"],
            -metric["threshold"],
        ),
    )
    return {
        "context_inclusion": round(context_best["threshold"], 4),
        "deterministic_answer": round(
            deterministic_best["threshold"],
            4,
        ),
        "context_metrics": context_best,
        "deterministic_metrics": deterministic_best,
        "deterministic_precision_min": deterministic_precision_min,
    }


def run(
    samples_path: Path | None = None,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    deterministic_precision_min: float = 0.98,
) -> dict[str, Any]:
    current = get_thresholds(registry_path)
    measured = samples_path is not None
    recommendation = (
        calibrate(
            load_labeled_scores(samples_path),
            deterministic_precision_min=deterministic_precision_min,
        )
        if samples_path
        else {
            "context_inclusion": current.context_inclusion,
            "deterministic_answer": current.deterministic_answer,
            "context_metrics": None,
            "deterministic_metrics": None,
            "deterministic_precision_min": (
                deterministic_precision_min
            ),
        }
    )

    report = build_stub_report("embedding", ("embedding-suz-recall",))
    report["report_id"] = report["report_id"].replace(
        "embedding-",
        "retrieval-thresholds-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = [REQUIREMENT]
    report["suite_details"] = {
        "test_type": "retrieval_threshold_calibration",
        "target_index": "cc_production",
        "current": {
            "context_inclusion": current.context_inclusion,
            "deterministic_answer": current.deterministic_answer,
            "status": current.status,
        },
        "recommended": recommendation,
        "recommendation_status": (
            "measured" if measured else "provisional_registry_defaults"
        ),
        "registry_written": False,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calibrate FR-LLM-04 retrieval thresholds.",
    )
    parser.add_argument(
        "--samples",
        type=Path,
        help="Labeled similarity-score JSON.",
    )
    parser.add_argument(
        "--deterministic-precision-min",
        type=float,
        default=0.98,
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=DEFAULT_REGISTRY_PATH,
    )
    parser.add_argument(
        "--write-registry",
        action="store_true",
    )
    parser.add_argument(
        "--sign-off",
        help="Approver/change-ticket reference required for frozen config.",
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
        args.samples,
        registry_path=args.registry,
        deterministic_precision_min=args.deterministic_precision_min,
    )
    if args.write_registry:
        if args.samples is None:
            print(
                "Registry was not changed: --write-registry requires "
                "measured --samples.",
                file=sys.stderr,
            )
            return 2
        if not args.sign_off:
            print(
                "Registry was not changed: --sign-off is required.",
                file=sys.stderr,
            )
            return 2
        recommended = report["suite_details"]["recommended"]
        expected_report_path = (
            args.output / f"{report['report_id']}.json"
        )
        set_thresholds(
            recommended["context_inclusion"],
            recommended["deterministic_answer"],
            args.registry,
            status="dev_frozen",
            benchmark_report=str(expected_report_path),
            sign_off=args.sign_off,
        )
        report["suite_details"]["registry_written"] = True

    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
