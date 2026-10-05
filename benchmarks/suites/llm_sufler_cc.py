"""Evaluate the ``sufler_cc`` ModelGateway profile on 20 RAG prompts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
for import_path in (REPOSITORY_ROOT, BACKEND_ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from benchmarks.suites.base import build_stub_report  # noqa: E402
from benchmarks.suites.embedding_recall import (  # noqa: E402
    DEFAULT_DATASET_PATH,
    load_dataset,
)
from core.model_gateway import ModelGateway  # noqa: E402


PROFILE = "sufler_cc"
EXPECTED_PROMPT_COUNT = 20
REQUIREMENTS = ("FR-LLM-06", "FR-LLM-07")


class LlmSuflerInputError(ValueError):
    """Raised when responses or manual rubric labels are malformed."""


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


def build_messages(sample: Mapping[str, Any]) -> list[dict[str, str]]:
    document = sample["document"]
    return [
        {
            "role": "system",
            "content": (
                "Ты суфлёр оператора Контакт-центра. Ответь только по "
                "предоставленному фрагменту СУЗ, кратко и без домыслов."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Источник: {document['title']}\n"
                f"Фрагмент СУЗ: {document['text']}\n"
                f"Вопрос клиента: {sample['query']}"
            ),
        },
    ]


def _response_text(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmSuflerInputError(
            "Gateway response has no assistant content"
        ) from exc
    if not isinstance(content, str):
        raise LlmSuflerInputError(
            "Gateway assistant content must be a string"
        )
    return content


def load_rubric(
    path: Path,
    expected_hashes: Mapping[str, str],
) -> dict[str, Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LlmSuflerInputError(f"Rubric not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LlmSuflerInputError(f"Invalid rubric JSON: {path}") from exc

    reviews = payload.get("reviews") if isinstance(payload, Mapping) else None
    if not isinstance(reviews, list):
        raise LlmSuflerInputError(
            "Rubric JSON must contain a 'reviews' list"
        )

    by_id: dict[str, Mapping[str, Any]] = {}
    for index, review in enumerate(reviews, start=1):
        if not isinstance(review, Mapping):
            raise LlmSuflerInputError(
                f"Rubric review #{index} must be an object"
            )
        sample_id = review.get("id")
        response_hash = review.get("response_sha256")
        hallucinated = review.get("hallucinated")
        if not isinstance(sample_id, str) or not sample_id:
            raise LlmSuflerInputError(
                f"Rubric review #{index} has invalid id"
            )
        if sample_id in by_id:
            raise LlmSuflerInputError(
                f"Duplicate rubric review id: {sample_id}"
            )
        if hallucinated not in {True, False}:
            raise LlmSuflerInputError(
                f"Rubric review {sample_id!r} requires hallucinated"
            )
        if response_hash != expected_hashes.get(sample_id):
            raise LlmSuflerInputError(
                f"Rubric response hash mismatch for {sample_id!r}"
            )
        by_id[sample_id] = review

    expected_ids = set(expected_hashes)
    if set(by_id) != expected_ids:
        raise LlmSuflerInputError(
            "Rubric ids must exactly match generated response ids"
        )
    return by_id


def run(
    *,
    gateway: ModelGateway | None = None,
    dataset_path: Path = DEFAULT_DATASET_PATH,
    rubric_path: Path | None = None,
) -> dict[str, Any]:
    samples = load_dataset(dataset_path)
    if len(samples) != EXPECTED_PROMPT_COUNT:
        raise LlmSuflerInputError(
            f"Suite requires exactly {EXPECTED_PROMPT_COUNT} prompts"
        )
    gateway = gateway or ModelGateway.from_registry()
    configured = gateway.get_profile(PROFILE)
    char_limit = int(configured.kpi["response_chars_max"])
    latency_limit_ms = int(configured.kpi["latency_p95_ms_max"])
    hallucination_limit = float(
        configured.kpi["hallucination_percent_max"]
    )
    mode_for = getattr(gateway, "_mode_for", lambda profile: profile.gateway_mode)
    is_stub = mode_for(configured) == "stub"

    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    for sample in samples:
        started_at = time.perf_counter()
        response = gateway.chat(PROFILE, build_messages(sample))
        latency_ms = (time.perf_counter() - started_at) * 1000
        text = _response_text(response)
        response_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        latencies.append(latency_ms)
        results.append(
            {
                "id": sample["id"],
                "document_id": sample["document"]["id"],
                "source_path": sample["document"]["source_path"],
                "query": sample["query"],
                "response": text,
                "response_sha256": response_hash,
                "chars": len(text),
                "chars_limit_passed": len(text) <= char_limit,
                "latency_ms": round(latency_ms, 2),
                "hallucinated": None,
                "hallucination_notes": None,
            }
        )

    rubric = (
        load_rubric(
            rubric_path,
            {result["id"]: result["response_sha256"] for result in results},
        )
        if rubric_path
        else None
    )
    if rubric:
        for result in results:
            review = rubric[result["id"]]
            result["hallucinated"] = review["hallucinated"]
            result["hallucination_notes"] = review.get("notes")

    reviewed = rubric is not None
    hallucination_rate = (
        sum(result["hallucinated"] for result in results)
        / len(results)
        * 100
        if reviewed
        else None
    )
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    char_pass_count = sum(
        result["chars_limit_passed"] for result in results
    )
    measured_model = not is_stub

    report = build_stub_report("llm", ("embedding-suz-recall",))
    report["report_id"] = report["report_id"].replace(
        "llm-",
        "llm-sufler-cc-",
        1,
    )
    report["runner_status"] = (
        "stub"
        if is_stub
        else "ready"
        if reviewed
        else "partial"
    )
    report["requirements"] = list(REQUIREMENTS)
    report["metrics"]["latency_ms"] = {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "status": "measured" if measured_model else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "llm_sufler_cc",
        "profile": PROFILE,
        "model": configured.model,
        "prompt_count": len(samples),
        "kpi_evidence": measured_model and reviewed,
        "characters": {
            "limit_max": char_limit,
            "passed": char_pass_count,
            "failed": len(results) - char_pass_count,
            "pass_rate_percent": round(
                char_pass_count / len(results) * 100,
                2,
            ),
            "status": "measured" if measured_model else "placeholder",
        },
        "latency": {
            "target_p95_ms_max": latency_limit_ms,
            "target_passed": (
                p95 <= latency_limit_ms if measured_model else None
            ),
        },
        "hallucination": {
            "rate_percent": (
                round(hallucination_rate, 2)
                if hallucination_rate is not None
                else None
            ),
            "target_percent_max": hallucination_limit,
            "target_passed": (
                hallucination_rate <= hallucination_limit
                if reviewed and measured_model
                else None
            ),
            "status": (
                "measured"
                if reviewed and measured_model
                else "manual_review_pending"
                if not reviewed
                else "rubric_on_stub_not_kpi"
            ),
            "resolution_note": (
                "With 20 prompts, one hallucination equals 5%; "
                "the <=3% KPI needs a larger sign-off dataset."
            ),
        },
        "results": results,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate the ModelGateway sufler_cc profile.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--rubric",
        type=Path,
        help="Manual hallucination reviews for this exact response set.",
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
    report = run(
        gateway=gateway,
        dataset_path=args.dataset,
        rubric_path=args.rubric,
    )
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
