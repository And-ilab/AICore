"""Evaluate RU/EN intent consistency for FR-UND-05 and SUF-T-12."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.suites.base import build_stub_report  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "qu_bilingual.json"
)
EXPECTED_SAMPLE_COUNT = 10
REQUIREMENT = "FR-UND-05"
ACCEPTANCE_TEST = "SUF-T-12"
LANGUAGES = ("ru", "en")


class QuBilingualInputError(ValueError):
    """Raised when bilingual data cannot be compared."""


def load_dataset(
    path: Path = DEFAULT_DATASET_PATH,
) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuBilingualInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise QuBilingualInputError(
            f"Invalid dataset JSON: {path}"
        ) from exc

    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or len(samples) != EXPECTED_SAMPLE_COUNT:
        raise QuBilingualInputError(
            f"Dataset must contain exactly {EXPECTED_SAMPLE_COUNT} samples"
        )

    sample_ids: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise QuBilingualInputError(
                f"Sample #{index} must be an object"
            )
        sample_id = sample.get("id")
        scenario_id = sample.get("source_scenario_id")
        expected_intent = sample.get("expected_intent_id")
        if not isinstance(sample_id, str) or not sample_id:
            raise QuBilingualInputError(
                f"Sample #{index} has invalid id"
            )
        if sample_id in sample_ids:
            raise QuBilingualInputError(f"Duplicate sample id: {sample_id}")
        if (
            not isinstance(scenario_id, str)
            or re.fullmatch(r"CC-SCR-\d{3}", scenario_id) is None
        ):
            raise QuBilingualInputError(
                f"Sample {sample_id!r} has invalid CC-SCR source"
            )
        if expected_intent != scenario_id:
            raise QuBilingualInputError(
                f"Sample {sample_id!r} intent must match source scenario"
            )
        for language in LANGUAGES:
            text = sample.get(f"{language}_text")
            if not isinstance(text, str) or not text.strip():
                raise QuBilingualInputError(
                    f"Sample {sample_id!r} requires {language}_text"
                )
        sample_ids.add(sample_id)
    return samples


def _validate_language_prediction(
    sample_id: str,
    language: str,
    value: Any,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QuBilingualInputError(
            f"Prediction {sample_id!r} requires {language} result"
        )
    matched = value.get("matched")
    intent_id = value.get("intent_id")
    score = value.get("relevance_score")
    if not isinstance(matched, bool):
        raise QuBilingualInputError(
            f"Prediction {sample_id!r}/{language} requires matched"
        )
    if intent_id is not None and not isinstance(intent_id, str):
        raise QuBilingualInputError(
            f"Prediction {sample_id!r}/{language} has invalid intent"
        )
    if score is not None and (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not 0 <= score <= 1
    ):
        raise QuBilingualInputError(
            f"Prediction {sample_id!r}/{language} has invalid score"
        )
    return value


def load_predictions(
    path: Path,
    expected_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QuBilingualInputError(
            f"Predictions not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise QuBilingualInputError(
            f"Invalid predictions JSON: {path}"
        ) from exc

    predictions = (
        payload.get("predictions")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(predictions, list):
        raise QuBilingualInputError(
            "Predictions JSON must contain a 'predictions' list"
        )

    by_id: dict[str, Mapping[str, Any]] = {}
    for index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, Mapping):
            raise QuBilingualInputError(
                f"Prediction #{index} must be an object"
            )
        sample_id = prediction.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise QuBilingualInputError(
                f"Prediction #{index} has invalid id"
            )
        if sample_id in by_id:
            raise QuBilingualInputError(
                f"Duplicate prediction id: {sample_id}"
            )
        for language in LANGUAGES:
            _validate_language_prediction(
                sample_id,
                language,
                prediction.get(language),
            )
        by_id[sample_id] = prediction

    prediction_ids = set(by_id)
    if prediction_ids != expected_ids:
        raise QuBilingualInputError(
            "Prediction ids must exactly match dataset ids; "
            f"missing={sorted(expected_ids - prediction_ids)}, "
            f"unknown={sorted(prediction_ids - expected_ids)}"
        )
    return by_id


def evaluate(
    samples: Sequence[Mapping[str, Any]],
    predictions: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    details: list[dict[str, Any]] = []
    for sample in samples:
        prediction = predictions[str(sample["id"])]
        expected_intent = sample["expected_intent_id"]
        ru = prediction["ru"]
        en = prediction["en"]
        ru_passed = ru["matched"] and ru.get("intent_id") == expected_intent
        en_passed = en["matched"] and en.get("intent_id") == expected_intent
        consistent = (
            ru["matched"]
            and en["matched"]
            and ru.get("intent_id") == en.get("intent_id")
        )
        details.append(
            {
                "id": sample["id"],
                "source_scenario_id": sample["source_scenario_id"],
                "expected_intent_id": expected_intent,
                "ru_intent_id": ru.get("intent_id"),
                "en_intent_id": en.get("intent_id"),
                "ru_relevance_score": ru.get("relevance_score"),
                "en_relevance_score": en.get("relevance_score"),
                "ru_passed": ru_passed,
                "en_passed": en_passed,
                "cross_language_consistent": consistent,
                "passed": ru_passed and en_passed and consistent,
            }
        )

    total = len(details)
    rates = {
        "ru_match_rate_percent": round(
            sum(item["ru_passed"] for item in details) / total * 100,
            2,
        ),
        "en_match_rate_percent": round(
            sum(item["en_passed"] for item in details) / total * 100,
            2,
        ),
        "cross_language_consistency_percent": round(
            sum(
                item["cross_language_consistent"] for item in details
            )
            / total
            * 100,
            2,
        ),
        "pair_pass_rate_percent": round(
            sum(item["passed"] for item in details) / total * 100,
            2,
        ),
    }
    return rates, details


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
        rates, details = evaluate(samples, predictions)
    else:
        rates = {
            "ru_match_rate_percent": None,
            "en_match_rate_percent": None,
            "cross_language_consistency_percent": None,
            "pair_pass_rate_percent": None,
        }
        details = []

    report = build_stub_report("qu", ("qu-cc-bilingual-pairs",))
    report["report_id"] = report["report_id"].replace(
        "qu-",
        "qu-bilingual-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["accuracy_percent"] = {
        "value": rates["pair_pass_rate_percent"],
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "qu_bilingual",
        "architecture": "hybrid",
        "acceptance_tests": [ACCEPTANCE_TEST],
        "sample_count": len(samples),
        "match_rates": rates,
        "overall_passed": (
            all(item["passed"] for item in details)
            if measured
            else None
        ),
        "results": details,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate same-intent matching in RU and EN.",
    )
    parser.add_argument("--predictions", type=Path)
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
