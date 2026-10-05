"""Evaluate OCR document classification and required-field extraction."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "ocr_samples.json"
)
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.suites.base import build_stub_report  # noqa: E402


REQUIREMENTS = (
    "FR-OCR-06",
    "FR-OCR-07",
    "FR-OCR-13",
    "FR-OCR-14",
    "FR-OCR-18",
)
ACCEPTANCE_TESTS = ("DOC-T-01", "DOC-T-03", "DOC-T-04")


class OcrExtractionInputError(ValueError):
    """Raised when OCR fixtures or candidate predictions are malformed."""


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OcrExtractionInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OcrExtractionInputError(
            f"Invalid dataset JSON: {path}"
        ) from exc
    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or not samples:
        raise OcrExtractionInputError(
            "OCR dataset requires a non-empty samples list"
        )
    seen_ids: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise OcrExtractionInputError(
                f"OCR sample #{index} must be an object"
            )
        sample_id = sample.get("id")
        input_data = sample.get("input")
        expected = sample.get("expected")
        if not isinstance(sample_id, str) or not sample_id:
            raise OcrExtractionInputError(
                f"OCR sample #{index} requires id"
            )
        if sample_id in seen_ids:
            raise OcrExtractionInputError(
                f"Duplicate OCR sample id: {sample_id}"
            )
        seen_ids.add(sample_id)
        if not isinstance(input_data, Mapping) or not isinstance(
            input_data.get("document_path"),
            str,
        ):
            raise OcrExtractionInputError(
                f"OCR sample {sample_id!r} requires document_path"
            )
        if not isinstance(expected, Mapping) or not isinstance(
            expected.get("document_type"),
            str,
        ):
            raise OcrExtractionInputError(
                f"OCR sample {sample_id!r} requires document_type"
            )
        fields = expected.get("fields")
        if (
            not isinstance(fields, list)
            or not fields
            or not all(isinstance(field, str) and field for field in fields)
            or len(fields) != len(set(fields))
        ):
            raise OcrExtractionInputError(
                f"OCR sample {sample_id!r} requires unique fields"
            )
    return samples


def load_predictions(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OcrExtractionInputError(
            f"Predictions not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise OcrExtractionInputError(
            f"Invalid predictions JSON: {path}"
        ) from exc
    predictions = (
        payload.get("predictions")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(predictions, list):
        raise OcrExtractionInputError(
            "Predictions JSON requires a 'predictions' list"
        )
    return predictions


def build_stub_predictions(
    samples: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": sample["id"],
            "document_type": "unknown",
            "fields": {},
            "status": "stub",
        }
        for sample in samples
    ]


def _has_extracted_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def evaluate_predictions(
    samples: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    predictions_by_id: dict[str, Mapping[str, Any]] = {}
    for index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, Mapping):
            raise OcrExtractionInputError(
                f"Prediction #{index} must be an object"
            )
        prediction_id = prediction.get("id")
        if not isinstance(prediction_id, str) or not prediction_id:
            raise OcrExtractionInputError(
                f"Prediction #{index} requires id"
            )
        if prediction_id in predictions_by_id:
            raise OcrExtractionInputError(
                f"Duplicate prediction id: {prediction_id}"
            )
        if not isinstance(prediction.get("document_type"), str):
            raise OcrExtractionInputError(
                f"Prediction {prediction_id!r} requires document_type"
            )
        if not isinstance(prediction.get("fields"), Mapping):
            raise OcrExtractionInputError(
                f"Prediction {prediction_id!r} requires fields object"
            )
        predictions_by_id[prediction_id] = prediction

    expected_ids = {sample["id"] for sample in samples}
    if set(predictions_by_id) != expected_ids:
        missing = sorted(expected_ids - set(predictions_by_id))
        unexpected = sorted(set(predictions_by_id) - expected_ids)
        raise OcrExtractionInputError(
            "Prediction ids must exactly match dataset ids; "
            f"missing={missing}, unexpected={unexpected}"
        )

    results: list[dict[str, Any]] = []
    aggregates: dict[str, dict[str, int]] = {}
    total_expected = 0
    total_extracted = 0
    total_extra = 0
    type_matches = 0
    available_files = 0

    for sample in samples:
        prediction = predictions_by_id[sample["id"]]
        expected = sample["expected"]
        expected_fields = set(expected["fields"])
        predicted_values = prediction["fields"]
        extracted_fields = {
            field
            for field, value in predicted_values.items()
            if _has_extracted_value(value)
        }
        matched = expected_fields & extracted_fields
        missing = expected_fields - extracted_fields
        extra = extracted_fields - expected_fields
        document_type = expected["document_type"]
        type_match = prediction["document_type"] == document_type
        type_matches += int(type_match)
        total_expected += len(expected_fields)
        total_extracted += len(matched)
        total_extra += len(extra)
        document_path = REPOSITORY_ROOT / sample["input"]["document_path"]
        file_exists = document_path.is_file()
        available_files += int(file_exists)

        aggregate = aggregates.setdefault(
            document_type,
            {
                "documents": 0,
                "expected_fields": 0,
                "extracted_required_fields": 0,
                "extra_fields": 0,
                "type_matches": 0,
            },
        )
        aggregate["documents"] += 1
        aggregate["expected_fields"] += len(expected_fields)
        aggregate["extracted_required_fields"] += len(matched)
        aggregate["extra_fields"] += len(extra)
        aggregate["type_matches"] += int(type_match)
        results.append(
            {
                "id": sample["id"],
                "document_path": sample["input"]["document_path"],
                "file_exists": file_exists,
                "mime_type": sample["input"]["mime_type"],
                "expected_document_type": document_type,
                "predicted_document_type": prediction["document_type"],
                "document_type_match": type_match,
                "expected_fields": sorted(expected_fields),
                "extracted_required_fields": sorted(matched),
                "missing_fields": sorted(missing),
                "extra_fields": sorted(extra),
                "field_accuracy_percent": round(
                    len(matched) / len(expected_fields) * 100,
                    2,
                ),
            }
        )

    by_document_type = {
        document_type: {
            **values,
            "field_accuracy_percent": round(
                values["extracted_required_fields"]
                / values["expected_fields"]
                * 100,
                2,
            ),
            "document_type_accuracy_percent": round(
                values["type_matches"] / values["documents"] * 100,
                2,
            ),
        }
        for document_type, values in sorted(aggregates.items())
    }
    field_accuracy = (
        total_extracted / total_expected * 100 if total_expected else 0.0
    )
    field_precision = (
        total_extracted / (total_extracted + total_extra) * 100
        if total_extracted + total_extra
        else 0.0
    )
    return {
        "field_accuracy_percent": round(field_accuracy, 2),
        "field_precision_percent": round(field_precision, 2),
        "document_type_accuracy_percent": round(
            type_matches / len(samples) * 100,
            2,
        ),
        "expected_field_count": total_expected,
        "extracted_required_field_count": total_extracted,
        "extra_field_count": total_extra,
        "available_sample_files": available_files,
        "sample_count": len(samples),
        "by_document_type": by_document_type,
        "results": results,
    }


def run(
    *,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    predictions_path: Path | None = None,
) -> dict[str, Any]:
    samples = load_dataset(dataset_path)
    measured = predictions_path is not None
    predictions = (
        load_predictions(predictions_path)
        if predictions_path
        else build_stub_predictions(samples)
    )
    evaluation = evaluate_predictions(samples, predictions)

    report = build_stub_report("ocr", ("ocr-synthetic-samples",))
    report["report_id"] = report["report_id"].replace(
        "ocr-",
        "ocr-extraction-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["accuracy_percent"] = {
        "value": evaluation["field_accuracy_percent"],
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "ocr_extraction",
        "acceptance_tests": list(ACCEPTANCE_TESTS),
        "predictions_supplied": measured,
        "kpi_evidence": (
            measured
            and evaluation["available_sample_files"]
            == evaluation["sample_count"]
        ),
        "scoring_scope": (
            "Non-empty required field extraction. Exact value accuracy "
            "requires gold field values not present in the stub dataset."
        ),
        **evaluation,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate Part IV OCR field extraction.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="Candidate OCR output JSON; omitted means stub.",
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
        dataset_path=args.dataset,
        predictions_path=args.predictions,
    )
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
