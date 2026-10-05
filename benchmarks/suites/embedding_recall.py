"""Recall@5 benchmark stub for synthetic SUZ-like documents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.suites.base import build_stub_report  # noqa: E402


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT
    / "benchmarks"
    / "datasets"
    / "embedding_recall.json"
)
EXPECTED_SAMPLE_COUNT = 20
TOP_K = 5
REQUIREMENTS = ("FR-LLM-03", "FR-LLM-04", "FR-LLM-05")
CANDIDATES = (
    {
        "id": "multilingual-e5-large",
        "model": "intfloat/multilingual-e5-large",
    },
    {
        "id": "bge-m3",
        "model": "BAAI/bge-m3",
    },
    {
        "id": "gte-multilingual-base",
        "model": "Alibaba-NLP/gte-multilingual-base",
    },
    {
        "id": "paraphrase-multilingual-mpnet-base-v2",
        "model": (
            "sentence-transformers/"
            "paraphrase-multilingual-mpnet-base-v2"
        ),
    },
)


class EmbeddingRecallInputError(ValueError):
    """Raised when the recall dataset cannot produce comparable runs."""


def load_dataset(
    path: Path = DEFAULT_DATASET_PATH,
) -> list[Mapping[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EmbeddingRecallInputError(
            f"Dataset not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise EmbeddingRecallInputError(
            f"Invalid dataset JSON: {path}"
        ) from exc

    samples = payload.get("samples") if isinstance(payload, Mapping) else None
    if not isinstance(samples, list):
        raise EmbeddingRecallInputError(
            "Dataset 'samples' must be a list"
        )
    if len(samples) != EXPECTED_SAMPLE_COUNT:
        raise EmbeddingRecallInputError(
            f"Dataset must contain exactly {EXPECTED_SAMPLE_COUNT} samples"
        )

    document_ids: set[str] = set()
    relevant_ids: set[str] = set()
    for index, sample in enumerate(samples, start=1):
        if not isinstance(sample, Mapping):
            raise EmbeddingRecallInputError(
                f"Sample #{index} must be an object"
            )
        document = sample.get("document")
        expected = sample.get("expected")
        query = sample.get("query")
        if not isinstance(document, Mapping):
            raise EmbeddingRecallInputError(
                f"Sample #{index} requires a document"
            )
        document_id = document.get("id")
        if not isinstance(document_id, str) or not document_id:
            raise EmbeddingRecallInputError(
                f"Sample #{index} has an invalid document id"
            )
        if document_id in document_ids:
            raise EmbeddingRecallInputError(
                f"Duplicate document id: {document_id}"
            )
        if not isinstance(query, str) or not query.strip():
            raise EmbeddingRecallInputError(
                f"Sample #{index} requires a query"
            )
        if not isinstance(expected, Mapping):
            raise EmbeddingRecallInputError(
                f"Sample #{index} requires expected labels"
            )
        labels = expected.get("relevant_document_ids")
        if not isinstance(labels, list) or not all(
            isinstance(label, str) and label for label in labels
        ):
            raise EmbeddingRecallInputError(
                f"Sample #{index} has invalid relevant document ids"
            )
        document_ids.add(document_id)
        relevant_ids.update(labels)

    unknown_labels = relevant_ids - document_ids
    if unknown_labels:
        labels = ", ".join(sorted(unknown_labels))
        raise EmbeddingRecallInputError(
            f"Relevant document ids are absent from corpus: {labels}"
        )
    return samples


def run(
    dataset_path: Path = DEFAULT_DATASET_PATH,
) -> dict[str, Any]:
    """Build a candidate report without fabricating embedding scores."""
    samples = load_dataset(dataset_path)
    report = build_stub_report("embedding", ("embedding-suz-recall",))
    report["report_id"] = report["report_id"].replace(
        "embedding-",
        "embedding-recall-",
        1,
    )
    report["requirements"] = list(REQUIREMENTS)
    report["suite_details"] = {
        "test_type": "embedding_recall",
        "metric": "recall@5",
        "top_k": TOP_K,
        "sample_count": len(samples),
        "corpus_document_count": len(samples),
        "query_count": len(samples),
        "candidate_results": [
            {
                **candidate,
                "recall_at_5_percent": None,
                "status": "placeholder",
            }
            for candidate in CANDIDATES
        ],
        "calibration_grid": {
            "chunk_size_tokens": [256, 512, 1024],
            "chunk_overlap_tokens": [50, 100, 200],
            "similarity_threshold": [0.6, 0.7, 0.8],
        },
        "note": (
            "No embedding model is invoked; measured values must replace "
            "placeholders after model adapters are connected."
        ),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create the embedding recall@5 candidate stub report.",
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
        help="Report directory (default: reports/).",
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
    report = run(args.dataset)
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
