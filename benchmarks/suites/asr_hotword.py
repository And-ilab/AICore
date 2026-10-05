"""Compare banking-term recognition with and without hotword boost.

Mapping: FR-ASR-09 requires specialized dictionaries for banking terms,
abbreviations, and contractions in real-time ASR.

The suite evaluates two transcript sets produced from the same audio samples.
It intentionally does not synthesize recognition results or emulate a
vendor-specific boost mechanism.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "datasets" / "asr_bank_terms.json"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT / "benchmarks" / "results" / "asr_hotword.json"
)
REQUIREMENT_ID = "FR-ASR-09"
EXPECTED_TERM_COUNT = 50


class BenchmarkInputError(ValueError):
    """Raised when benchmark data is incomplete or malformed."""


@dataclass(frozen=True)
class BankTerm:
    id: str
    term: str
    aliases: tuple[str, ...] = ()


def normalize_text(value: str) -> str:
    """Normalize ASR text for phrase-level term matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("ё", "е").replace("_", " ")
    return re.sub(r"[^\w]+", " ", normalized, flags=re.UNICODE).strip()


def contains_term(transcript: str, term: BankTerm) -> bool:
    """Return whether a transcript contains the term or an accepted alias."""
    normalized_transcript = f" {normalize_text(transcript)} "
    candidates = (term.term, *term.aliases)
    return any(
        f" {normalize_text(candidate)} " in normalized_transcript
        for candidate in candidates
    )


def load_dataset(path: Path = DEFAULT_DATASET_PATH) -> list[BankTerm]:
    """Load and validate the canonical 50-term banking dataset."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkInputError(f"Dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkInputError(f"Invalid dataset JSON: {path}") from exc

    if not isinstance(payload, Mapping):
        raise BenchmarkInputError("Dataset root must be an object")
    source = payload.get("source")
    requirement = payload.get("requirement")
    if requirement is None and isinstance(source, Mapping):
        requirement = source.get("requirement")
    if requirement != REQUIREMENT_ID:
        raise BenchmarkInputError(
            f"Dataset must map to {REQUIREMENT_ID}"
        )
    raw_terms = payload.get("samples", payload.get("terms"))
    if not isinstance(raw_terms, list):
        raise BenchmarkInputError("Dataset 'samples' must be a list")
    if len(raw_terms) != EXPECTED_TERM_COUNT:
        raise BenchmarkInputError(
            f"Dataset must contain exactly {EXPECTED_TERM_COUNT} terms"
        )

    terms: list[BankTerm] = []
    for index, raw_term in enumerate(raw_terms, start=1):
        if not isinstance(raw_term, Mapping):
            raise BenchmarkInputError(
                f"Dataset term #{index} must be an object"
            )
        term_id = raw_term.get("id")
        term = raw_term.get("term")
        aliases = raw_term.get("aliases", [])
        if not isinstance(term_id, str) or not term_id:
            raise BenchmarkInputError(
                f"Dataset term #{index} has an invalid id"
            )
        if not isinstance(term, str) or not term:
            raise BenchmarkInputError(
                f"Dataset term {term_id!r} has an invalid term"
            )
        if not isinstance(aliases, list) or not all(
            isinstance(alias, str) and alias for alias in aliases
        ):
            raise BenchmarkInputError(
                f"Dataset term {term_id!r} has invalid aliases"
            )
        terms.append(BankTerm(term_id, term, tuple(aliases)))

    term_ids = [term.id for term in terms]
    if len(set(term_ids)) != len(term_ids):
        raise BenchmarkInputError("Dataset term ids must be unique")
    return terms


def load_recognitions(path: Path) -> dict[str, str]:
    """Load transcripts keyed by dataset term id.

    Supported JSON shapes:
    - {"recognitions": [{"id": "bank-001", "text": "..."}]}
    - [{"id": "bank-001", "text": "..."}]
    - {"bank-001": "..."}
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BenchmarkInputError(
            f"Recognition results not found: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise BenchmarkInputError(
            f"Invalid recognition results JSON: {path}"
        ) from exc

    if isinstance(payload, Mapping) and "recognitions" in payload:
        payload = payload["recognitions"]
    if isinstance(payload, Mapping):
        if not all(
            isinstance(term_id, str) and isinstance(text, str)
            for term_id, text in payload.items()
        ):
            raise BenchmarkInputError(
                "Recognition mapping must contain string ids and texts"
            )
        return dict(payload)
    if not isinstance(payload, list):
        raise BenchmarkInputError(
            "Recognition results must be a list or object"
        )

    recognitions: dict[str, str] = {}
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, Mapping):
            raise BenchmarkInputError(
                f"Recognition #{index} must be an object"
            )
        term_id = item.get("id")
        text = item.get("text")
        if not isinstance(term_id, str) or not isinstance(text, str):
            raise BenchmarkInputError(
                f"Recognition #{index} requires string id and text"
            )
        if term_id in recognitions:
            raise BenchmarkInputError(
                f"Duplicate recognition id: {term_id}"
            )
        recognitions[term_id] = text
    return recognitions


def _mode_summary(
    terms: Sequence[BankTerm],
    recognitions: Mapping[str, str],
) -> dict[str, Any]:
    correct = sum(
        contains_term(recognitions.get(term.id, ""), term)
        for term in terms
    )
    total = len(terms)
    return {
        "correct": correct,
        "total": total,
        "term_accuracy_percent": round(correct / total * 100, 2),
        "missing_transcripts": [
            term.id for term in terms if term.id not in recognitions
        ],
    }


def evaluate(
    terms: Sequence[BankTerm],
    without_boost: Mapping[str, str],
    with_boost: Mapping[str, str],
    *,
    dataset_name: str = "asr-bank-terms",
) -> dict[str, Any]:
    """Build an FR-ASR-09 comparison report from paired transcripts."""
    known_ids = {term.id for term in terms}
    unknown_ids = (
        set(without_boost) | set(with_boost)
    ) - known_ids
    if unknown_ids:
        ids = ", ".join(sorted(unknown_ids))
        raise BenchmarkInputError(
            f"Recognition results contain unknown ids: {ids}"
        )

    baseline = _mode_summary(terms, without_boost)
    boosted = _mode_summary(terms, with_boost)
    details = []
    for term in terms:
        baseline_text = without_boost.get(term.id, "")
        boosted_text = with_boost.get(term.id, "")
        baseline_correct = contains_term(baseline_text, term)
        boosted_correct = contains_term(boosted_text, term)
        details.append(
            {
                "id": term.id,
                "term": term.term,
                "without_hotword_boost": {
                    "text": baseline_text,
                    "correct": baseline_correct,
                },
                "with_hotword_boost": {
                    "text": boosted_text,
                    "correct": boosted_correct,
                },
                "improved": not baseline_correct and boosted_correct,
            }
        )

    return {
        "suite": "asr_hotword",
        "requirement": REQUIREMENT_ID,
        "dataset": dataset_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_terms": len(terms),
        "without_hotword_boost": baseline,
        "with_hotword_boost": boosted,
        "improvement_percentage_points": round(
            boosted["term_accuracy_percent"]
            - baseline["term_accuracy_percent"],
            2,
        ),
        "terms": details,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare FR-ASR-09 banking-term accuracy with and without "
            "hotword boost."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET_PATH,
    )
    parser.add_argument(
        "--without-boost",
        type=Path,
        required=True,
        help="JSON transcripts produced without hotword boost.",
    )
    parser.add_argument(
        "--with-boost",
        type=Path,
        required=True,
        help="JSON transcripts produced with hotword boost.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    terms = load_dataset(args.dataset)
    without_boost = load_recognitions(args.without_boost)
    with_boost = load_recognitions(args.with_boost)
    report = evaluate(terms, without_boost, with_boost)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "FR-ASR-09 term accuracy: "
        f"{report['without_hotword_boost']['term_accuracy_percent']}% "
        "without boost, "
        f"{report['with_hotword_boost']['term_accuracy_percent']}% "
        "with boost "
        f"({report['improvement_percentage_points']:+.2f} pp)."
    )
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
