"""Benchmark OCR text to structured JSON through the ``docs_ocr`` profile."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "ocr_samples.json"
)
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from core.model_gateway import ModelGateway  # noqa: E402


PROFILE = "docs_ocr"
REQUIREMENTS = (
    "FR-OCR-01",
    "FR-OCR-02",
    "FR-OCR-13",
    "FR-OCR-14",
    "FR-OCR-22",
    "FR-LLM-07",
)


class LlmDocsOcrInputError(ValueError):
    """Raised when the dataset or gateway output is malformed."""


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


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LlmDocsOcrInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LlmDocsOcrInputError(f"Invalid dataset JSON: {path}") from exc
    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or not samples:
        raise LlmDocsOcrInputError("Dataset requires a non-empty samples list")
    seen_ids: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise LlmDocsOcrInputError(
                f"Dataset sample #{index} must be an object"
            )
        sample_id = sample.get("id")
        input_data = sample.get("input")
        expected = sample.get("expected")
        if not isinstance(sample_id, str) or not sample_id:
            raise LlmDocsOcrInputError(
                f"Dataset sample #{index} requires id"
            )
        if sample_id in seen_ids:
            raise LlmDocsOcrInputError(f"Duplicate sample id: {sample_id}")
        seen_ids.add(sample_id)
        if not isinstance(input_data, Mapping) or not isinstance(
            input_data.get("ocr_text"),
            str,
        ):
            raise LlmDocsOcrInputError(
                f"Dataset sample {sample_id!r} requires input.ocr_text"
            )
        if not isinstance(expected, Mapping) or not isinstance(
            expected.get("document_type"),
            str,
        ):
            raise LlmDocsOcrInputError(
                f"Dataset sample {sample_id!r} requires document_type"
            )
        fields = expected.get("fields")
        if (
            not isinstance(fields, list)
            or not fields
            or not all(isinstance(field, str) and field for field in fields)
        ):
            raise LlmDocsOcrInputError(
                f"Dataset sample {sample_id!r} requires expected fields"
            )
    return samples


def build_messages(sample: Mapping[str, Any]) -> list[dict[str, str]]:
    input_data = sample["input"]
    expected = sample["expected"]
    field_template = ", ".join(expected["fields"])
    return [
        {
            "role": "system",
            "content": (
                "Ты валидатор OCR. Верни только JSON с ключами "
                "document_type, fields и validation. Не додумывай "
                "отсутствующие значения."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Шаблон типа: {expected['document_type']}\n"
                f"Обязательные поля: {field_template}\n"
                f"Язык: {input_data['language']}\n"
                f"OCR-текст:\n{input_data['ocr_text']}"
            ),
        },
    ]


def _structured_content(
    response: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmDocsOcrInputError(
            "Gateway response has no assistant content"
        ) from exc
    if not isinstance(content, str):
        raise LlmDocsOcrInputError(
            "Gateway assistant content must be a JSON string"
        )
    try:
        structured = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LlmDocsOcrInputError(
            "Gateway assistant content is not valid JSON"
        ) from exc
    if not isinstance(structured, Mapping):
        raise LlmDocsOcrInputError("Structured output must be an object")
    if not isinstance(structured.get("document_type"), str):
        raise LlmDocsOcrInputError(
            "Structured output requires document_type"
        )
    if not isinstance(structured.get("fields"), Mapping):
        raise LlmDocsOcrInputError("Structured output requires fields object")
    if not isinstance(structured.get("validation"), Mapping):
        raise LlmDocsOcrInputError(
            "Structured output requires validation object"
        )
    return content, structured


def run(
    *,
    gateway: ModelGateway | None = None,
    dataset_path: Path = DEFAULT_DATASET_PATH,
) -> dict[str, Any]:
    samples = load_dataset(dataset_path)
    gateway = gateway or ModelGateway.from_registry()
    configured = gateway.get_profile(PROFILE)
    mode_for = getattr(gateway, "_mode_for", lambda profile: profile.gateway_mode)
    is_stub = mode_for(configured) == "stub"
    latency_limit_ms = int(configured.kpi["latency_p95_ms_max"])

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    expected_field_count = 0
    matched_field_count = 0
    extra_field_count = 0
    document_type_matches = 0
    valid_json_count = 0

    for sample in samples:
        started_at = time.perf_counter()
        response = gateway.chat(PROFILE, build_messages(sample))
        latency_ms = (time.perf_counter() - started_at) * 1000
        latencies.append(latency_ms)
        expected = sample["expected"]
        expected_fields = set(expected["fields"])
        expected_field_count += len(expected_fields)
        raw_content = ""
        error: str | None = None
        structured: Mapping[str, Any] = {}
        try:
            raw_content, structured = _structured_content(response)
            valid_json_count += 1
        except LlmDocsOcrInputError as exc:
            error = str(exc)

        predicted_fields_value = structured.get("fields", {})
        predicted_fields = (
            set(predicted_fields_value)
            if isinstance(predicted_fields_value, Mapping)
            else set()
        )
        matched_fields = expected_fields & predicted_fields
        extra_fields = predicted_fields - expected_fields
        matched_field_count += len(matched_fields)
        extra_field_count += len(extra_fields)
        type_match = (
            structured.get("document_type")
            == expected["document_type"]
        )
        document_type_matches += int(type_match)
        results.append(
            {
                "id": sample["id"],
                "document_path": sample["input"]["document_path"],
                "expected_document_type": expected["document_type"],
                "predicted_document_type": structured.get(
                    "document_type"
                ),
                "document_type_match": type_match,
                "expected_fields": sorted(expected_fields),
                "predicted_fields": sorted(predicted_fields),
                "matched_fields": sorted(matched_fields),
                "missing_fields": sorted(
                    expected_fields - predicted_fields
                ),
                "extra_fields": sorted(extra_fields),
                "json_valid": error is None,
                "validation": structured.get("validation"),
                "raw_response": raw_content,
                "latency_ms": round(latency_ms, 2),
                "error": error,
            }
        )

    field_accuracy = (
        matched_field_count / expected_field_count * 100
        if expected_field_count
        else 0.0
    )
    field_precision = (
        matched_field_count
        / (matched_field_count + extra_field_count)
        * 100
        if matched_field_count + extra_field_count
        else 0.0
    )
    type_accuracy = document_type_matches / len(samples) * 100
    json_validity = valid_json_count / len(samples) * 100
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)

    report = build_stub_report("llm", ("ocr-synthetic-samples",))
    report["report_id"] = report["report_id"].replace(
        "llm-",
        "llm-docs-ocr-",
        1,
    )
    report["runner_status"] = "stub" if is_stub else "ready"
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["latency_ms"] = {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "status": "placeholder" if is_stub else "measured",
    }
    report["metrics"]["accuracy_percent"] = {
        "value": round(field_accuracy, 2),
        "status": "placeholder" if is_stub else "measured",
    }
    report["suite_details"] = {
        "test_type": "llm_docs_ocr",
        "profile": PROFILE,
        "model": configured.model,
        "sample_count": len(samples),
        "kpi_evidence": not is_stub,
        "field_extraction": {
            "accuracy_percent": round(field_accuracy, 2),
            "precision_percent": round(field_precision, 2),
            "matched_required_fields": matched_field_count,
            "expected_required_fields": expected_field_count,
            "extra_fields": extra_field_count,
            "scoring_scope": "required field-name presence",
            "status": "placeholder" if is_stub else "measured",
        },
        "document_type_accuracy_percent": round(type_accuracy, 2),
        "structured_json_validity_percent": round(json_validity, 2),
        "latency": {
            "target_p95_ms_max": latency_limit_ms,
            "target_passed": (
                p95 <= latency_limit_ms if not is_stub else None
            ),
        },
        "results": results,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate docs_ocr structured field extraction.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--mode",
        choices=("stub", "openai"),
        help="Optional ModelGateway mode override.",
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
    gateway = ModelGateway.from_registry(mode=args.mode)
    report = run(gateway=gateway, dataset_path=args.dataset)
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
