"""Evaluate exact source-chunk citations for FR-LLM-05 grounded RAG."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "rag_query_pairs.json"
)
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from benchmarks.suites.base import build_stub_report  # noqa: E402


REQUIREMENT = "FR-LLM-05"


class RagGroundingInputError(ValueError):
    """Raised when grounding cases or orchestrator predictions are invalid."""


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RagGroundingInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RagGroundingInputError(f"Invalid dataset JSON: {path}") from exc
    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list) or not samples:
        raise RagGroundingInputError(
            "Grounding dataset requires a non-empty samples list"
        )
    seen_ids: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise RagGroundingInputError(
                f"Grounding sample #{index} must be an object"
            )
        sample_id = sample.get("id")
        input_data = sample.get("input")
        expected = sample.get("expected")
        if not isinstance(sample_id, str) or not sample_id:
            raise RagGroundingInputError(
                f"Grounding sample #{index} requires id"
            )
        if sample_id in seen_ids:
            raise RagGroundingInputError(
                f"Duplicate grounding sample id: {sample_id}"
            )
        seen_ids.add(sample_id)
        if not isinstance(input_data, Mapping) or not isinstance(
            input_data.get("query"),
            str,
        ):
            raise RagGroundingInputError(
                f"Grounding sample {sample_id!r} requires input.query"
            )
        chunk_ids = (
            expected.get("source_chunk_ids")
            if isinstance(expected, Mapping)
            else None
        )
        if (
            not isinstance(chunk_ids, list)
            or not chunk_ids
            or not all(
                isinstance(chunk_id, str) and chunk_id
                for chunk_id in chunk_ids
            )
            or len(chunk_ids) != len(set(chunk_ids))
        ):
            raise RagGroundingInputError(
                f"Grounding sample {sample_id!r} requires unique "
                "source_chunk_ids"
            )
    return samples


def load_predictions(path: Path) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RagGroundingInputError(
            f"Predictions not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RagGroundingInputError(
            f"Invalid predictions JSON: {path}"
        ) from exc
    predictions = (
        payload.get("predictions")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(predictions, list):
        raise RagGroundingInputError(
            "Predictions JSON requires a 'predictions' list"
        )
    return predictions


def build_stub_predictions(
    samples: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build a contract fixture; these are not model-quality predictions."""
    return [
        {
            "id": sample["id"],
            "answer": "Stub grounded answer.",
            "citations": [
                {
                    "chunk_id": chunk_id,
                    "source_path": sample["expected"]["context_path"],
                }
                for chunk_id in sample["expected"]["source_chunk_ids"]
            ],
        }
        for sample in samples
    ]


def evaluate_predictions(
    samples: Sequence[Mapping[str, Any]],
    predictions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_ids = {sample["id"] for sample in samples}
    predictions_by_id: dict[str, Mapping[str, Any]] = {}
    for index, prediction in enumerate(predictions, start=1):
        if not isinstance(prediction, Mapping):
            raise RagGroundingInputError(
                f"Prediction #{index} must be an object"
            )
        prediction_id = prediction.get("id")
        if not isinstance(prediction_id, str) or not prediction_id:
            raise RagGroundingInputError(
                f"Prediction #{index} requires id"
            )
        if prediction_id in predictions_by_id:
            raise RagGroundingInputError(
                f"Duplicate prediction id: {prediction_id}"
            )
        predictions_by_id[prediction_id] = prediction
    if set(predictions_by_id) != expected_ids:
        missing = sorted(expected_ids - set(predictions_by_id))
        unexpected = sorted(set(predictions_by_id) - expected_ids)
        raise RagGroundingInputError(
            "Prediction ids must exactly match dataset ids; "
            f"missing={missing}, unexpected={unexpected}"
        )

    results: list[dict[str, Any]] = []
    exact_match_count = 0
    matched_total = 0
    expected_total = 0
    cited_total = 0
    invalid_total = 0
    duplicate_total = 0

    for sample in samples:
        prediction = predictions_by_id[sample["id"]]
        answer = prediction.get("answer")
        citations = prediction.get("citations")
        if not isinstance(answer, str):
            raise RagGroundingInputError(
                f"Prediction {sample['id']!r} requires answer"
            )
        if not isinstance(citations, list):
            raise RagGroundingInputError(
                f"Prediction {sample['id']!r} requires citations list"
            )
        cited_ids: list[str] = []
        for citation_index, citation in enumerate(citations, start=1):
            chunk_id = (
                citation.get("chunk_id")
                if isinstance(citation, Mapping)
                else None
            )
            if not isinstance(chunk_id, str) or not chunk_id:
                raise RagGroundingInputError(
                    f"Prediction {sample['id']!r} citation "
                    f"#{citation_index} requires chunk_id"
                )
            cited_ids.append(chunk_id)

        expected_chunk_ids = sample["expected"]["source_chunk_ids"]
        expected_set = set(expected_chunk_ids)
        cited_set = set(cited_ids)
        matched = expected_set & cited_set
        invalid = cited_set - expected_set
        missing = expected_set - cited_set
        duplicates = len(cited_ids) - len(cited_set)
        exact_match = (
            not duplicates
            and cited_set == expected_set
            and bool(cited_ids)
        )
        exact_match_count += int(exact_match)
        matched_total += len(matched)
        expected_total += len(expected_set)
        cited_total += len(cited_ids)
        invalid_total += len(invalid)
        duplicate_total += duplicates
        results.append(
            {
                "id": sample["id"],
                "query": sample["input"]["query"],
                "answer": answer,
                "expected_chunk_ids": sorted(expected_set),
                "cited_chunk_ids": cited_ids,
                "matched_chunk_ids": sorted(matched),
                "missing_chunk_ids": sorted(missing),
                "invalid_chunk_ids": sorted(invalid),
                "duplicate_citation_count": duplicates,
                "exact_match": exact_match,
            }
        )

    citation_accuracy = exact_match_count / len(samples) * 100
    citation_precision = (
        matched_total / cited_total * 100 if cited_total else 0.0
    )
    citation_recall = (
        matched_total / expected_total * 100
        if expected_total
        else 0.0
    )
    return {
        "citation_accuracy_percent": round(citation_accuracy, 2),
        "citation_precision_percent": round(citation_precision, 2),
        "citation_recall_percent": round(citation_recall, 2),
        "exact_match_count": exact_match_count,
        "case_count": len(samples),
        "matched_citation_count": matched_total,
        "expected_citation_count": expected_total,
        "cited_count": cited_total,
        "invalid_citation_count": invalid_total,
        "duplicate_citation_count": duplicate_total,
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

    report = build_stub_report("llm", ("rag-cc-query-pairs",))
    report["report_id"] = report["report_id"].replace(
        "llm-",
        "rag-grounding-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["accuracy_percent"] = {
        "value": evaluation["citation_accuracy_percent"],
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "rag_grounding",
        "target_orchestrator": "P3-04",
        "kpi_evidence": measured,
        "citation_accuracy": {
            key: value
            for key, value in evaluation.items()
            if key != "results"
        },
        "scoring_contract": {
            "primary_metric": "citation_accuracy_percent",
            "case_pass_rule": (
                "Cited chunk_id set exactly equals expected "
                "source_chunk_ids, with no duplicates."
            ),
            "prediction_schema": {
                "id": "dataset sample id",
                "answer": "generated answer text",
                "citations": [{"chunk_id": "SUZ/KB chunk id"}],
            },
        },
        "results": evaluation["results"],
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate FR-LLM-05 source-chunk grounding.",
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--predictions",
        type=Path,
        help="P3-04 orchestrator prediction JSON; omitted means stub.",
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
