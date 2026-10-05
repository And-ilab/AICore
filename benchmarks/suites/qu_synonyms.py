"""Evaluate hybrid QU predictions against CC-SCR semantic pairs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.suites.base import build_stub_report  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "qu_synonyms.json"
)
EXPECTED_SAMPLE_COUNT = 20
EXPECTED_CATEGORY_COUNTS = {
    "synonyms": 10,
    "antonyms": 5,
    "word_order": 5,
}
REQUIREMENTS = ("FR-UND-04", "FR-UND-06")


class QuSynonymsInputError(ValueError):
    """Raised when dataset or QU predictions are not comparable."""


def load_dataset(
    path: Path = DEFAULT_DATASET_PATH,
) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuSynonymsInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QuSynonymsInputError(f"Invalid dataset JSON: {path}") from exc

    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or len(samples) != EXPECTED_SAMPLE_COUNT:
        raise QuSynonymsInputError(
            f"Dataset must contain exactly {EXPECTED_SAMPLE_COUNT} samples"
        )

    sample_ids: set[str] = set()
    categories: Counter[str] = Counter()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise QuSynonymsInputError(
                f"Sample #{index} must be an object"
            )
        sample_id = sample.get("id")
        category = sample.get("category")
        source_scenario_id = sample.get("source_scenario_id")
        expected_match = sample.get("expected_match")
        expected_intent = sample.get("expected_intent_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise QuSynonymsInputError(
                f"Sample #{index} has invalid id"
            )
        if sample_id in sample_ids:
            raise QuSynonymsInputError(f"Duplicate sample id: {sample_id}")
        if category not in EXPECTED_CATEGORY_COUNTS:
            raise QuSynonymsInputError(
                f"Sample {sample_id!r} has invalid category"
            )
        if (
            not isinstance(source_scenario_id, str)
            or re.fullmatch(r"CC-SCR-\d{3}", source_scenario_id) is None
        ):
            raise QuSynonymsInputError(
                f"Sample {sample_id!r} has invalid CC-SCR source"
            )
        if not isinstance(expected_match, bool):
            raise QuSynonymsInputError(
                f"Sample {sample_id!r} requires expected_match"
            )
        if expected_match and (
            not isinstance(expected_intent, str)
            or not expected_intent
        ):
            raise QuSynonymsInputError(
                f"Matched sample {sample_id!r} requires expected intent"
            )
        if not expected_match and expected_intent is not None:
            raise QuSynonymsInputError(
                f"Rejected sample {sample_id!r} must use null intent"
            )
        for text_field in ("reference", "candidate"):
            if (
                not isinstance(sample.get(text_field), str)
                or not sample[text_field].strip()
            ):
                raise QuSynonymsInputError(
                    f"Sample {sample_id!r} requires {text_field}"
                )
        sample_ids.add(sample_id)
        categories[category] += 1

    if dict(categories) != EXPECTED_CATEGORY_COUNTS:
        raise QuSynonymsInputError(
            "Dataset category counts do not match the expected matrix"
        )
    return samples


def load_predictions(
    path: Path,
    expected_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuSynonymsInputError(
            f"Predictions not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise QuSynonymsInputError(
            f"Invalid predictions JSON: {path}"
        ) from exc

    predictions = (
        payload.get("predictions")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(predictions, list):
        raise QuSynonymsInputError(
            "Predictions JSON must contain a 'predictions' list"
        )

    by_id: dict[str, Mapping[str, Any]] = {}
    for index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, Mapping):
            raise QuSynonymsInputError(
                f"Prediction #{index} must be an object"
            )
        sample_id = prediction.get("id")
        matched = prediction.get("matched")
        predicted_intent = prediction.get("predicted_intent_id")
        score = prediction.get("relevance_score")
        if not isinstance(sample_id, str) or not sample_id:
            raise QuSynonymsInputError(
                f"Prediction #{index} has invalid id"
            )
        if sample_id in by_id:
            raise QuSynonymsInputError(
                f"Duplicate prediction id: {sample_id}"
            )
        if not isinstance(matched, bool):
            raise QuSynonymsInputError(
                f"Prediction {sample_id!r} requires boolean matched"
            )
        if predicted_intent is not None and not isinstance(
            predicted_intent,
            str,
        ):
            raise QuSynonymsInputError(
                f"Prediction {sample_id!r} has invalid intent"
            )
        if score is not None and (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= score <= 1
        ):
            raise QuSynonymsInputError(
                f"Prediction {sample_id!r} has invalid relevance score"
            )
        by_id[sample_id] = prediction

    prediction_ids = set(by_id)
    if prediction_ids != expected_ids:
        raise QuSynonymsInputError(
            "Prediction ids must exactly match dataset ids; "
            f"missing={sorted(expected_ids - prediction_ids)}, "
            f"unknown={sorted(prediction_ids - expected_ids)}"
        )
    return by_id


def evaluate(
    samples: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    for sample in samples:
        prediction = predictions[str(sample["id"])]
        match_correct = (
            prediction["matched"] == sample["expected_match"]
        )
        intent_correct = (
            not sample["expected_match"]
            or prediction.get("predicted_intent_id")
            == sample["expected_intent_id"]
        )
        details.append(
            {
                "id": sample["id"],
                "category": sample["category"],
                "source_scenario_id": sample["source_scenario_id"],
                "expected_match": sample["expected_match"],
                "actual_match": prediction["matched"],
                "expected_intent_id": sample["expected_intent_id"],
                "predicted_intent_id": prediction.get(
                    "predicted_intent_id"
                ),
                "relevance_score": prediction.get("relevance_score"),
                "passed": match_correct and intent_correct,
            }
        )

    categories: dict[str, Any] = {}
    for category in EXPECTED_CATEGORY_COUNTS:
        category_results = [
            result for result in details if result["category"] == category
        ]
        passed = sum(result["passed"] for result in category_results)
        total = len(category_results)
        categories[category] = {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate_percent": round(passed / total * 100, 2),
            "status": "passed" if passed == total else "failed",
        }
    return categories, details


def run(
    predictions_path: Path | None = None,
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
) -> dict[str, Any]:
    samples = load_dataset(dataset_path)
    measured = predictions_path is not None
    if measured:
        predictions = load_predictions(
            predictions_path,
            {str(sample["id"]) for sample in samples},
        )
        categories, details = evaluate(samples, predictions)
        passed = sum(result["passed"] for result in details)
        accuracy = round(passed / len(details) * 100, 2)
    else:
        categories = {
            category: {
                "total": total,
                "passed": None,
                "failed": None,
                "pass_rate_percent": None,
                "status": "placeholder",
            }
            for category, total in EXPECTED_CATEGORY_COUNTS.items()
        }
        details = []
        accuracy = None

    report = build_stub_report("qu", ("qu-cc-semantic-pairs",))
    report["report_id"] = report["report_id"].replace(
        "qu-",
        "qu-synonyms-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["accuracy_percent"] = {
        "value": accuracy,
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "qu_semantic_pairs",
        "architecture": "hybrid",
        "sample_count": len(samples),
        "categories": categories,
        "overall_passed": (
            all(result["passed"] for result in details)
            if measured
            else None
        ),
        "results": details,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate QU synonyms, antonyms, and word order.",
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Hybrid QU predictions for all dataset pair ids.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
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
    report = run(args.predictions, dataset_path=args.dataset)
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
