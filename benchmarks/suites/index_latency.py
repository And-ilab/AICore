"""Incremental-index searchability latency benchmark for FR-UND-08."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence


if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from benchmarks.suites.base import build_stub_report  # noqa: E402


UPDATE_COUNT = 30
ACCEPTANCE_LIMIT_MS = 120_000
OPERATIONAL_TARGET_P95_MS = 30_000
REQUIREMENT = "FR-UND-08"


class IndexLatencyInputError(ValueError):
    """Raised when index timing events are incomplete or invalid."""


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


def _parse_timestamp(value: Any, field: str, event_id: str) -> datetime:
    if not isinstance(value, str):
        raise IndexLatencyInputError(
            f"Event {event_id!r} field {field!r} must be ISO-8601"
        )
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IndexLatencyInputError(
            f"Event {event_id!r} has invalid {field!r}"
        ) from exc
    if timestamp.tzinfo is None:
        raise IndexLatencyInputError(
            f"Event {event_id!r} field {field!r} must include timezone"
        )
    return timestamp


def load_events(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IndexLatencyInputError(f"Events not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IndexLatencyInputError(f"Invalid events JSON: {path}") from exc

    events = payload.get("events") if isinstance(payload, Mapping) else None
    if not isinstance(events, list):
        raise IndexLatencyInputError("Input must contain an 'events' list")
    if len(events) != UPDATE_COUNT:
        raise IndexLatencyInputError(
            f"Exactly {UPDATE_COUNT} update events are required"
        )

    parsed: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for index, event in enumerate(events, start=1):
        if not isinstance(event, Mapping):
            raise IndexLatencyInputError(
                f"Event #{index} must be an object"
            )
        event_id = event.get("article_id")
        if not isinstance(event_id, str) or not event_id:
            raise IndexLatencyInputError(
                f"Event #{index} requires article_id"
            )
        if event_id in event_ids:
            raise IndexLatencyInputError(
                f"Duplicate article_id: {event_id}"
            )
        published_at = _parse_timestamp(
            event.get("published_at"),
            "published_at",
            event_id,
        )
        searchable_at = _parse_timestamp(
            event.get("searchable_at"),
            "searchable_at",
            event_id,
        )
        latency_ms = (searchable_at - published_at).total_seconds() * 1000
        if latency_ms < 0:
            raise IndexLatencyInputError(
                f"Event {event_id!r} became searchable before publication"
            )
        event_ids.add(event_id)
        parsed.append(
            {
                "article_id": event_id,
                "published_at": published_at.isoformat(),
                "searchable_at": searchable_at.isoformat(),
                "latency_ms": round(latency_ms, 2),
            }
        )
    return parsed


def placeholder_events() -> list[dict[str, Any]]:
    return [
        {
            "article_id": f"SUZ-UPDATE-{number:03d}",
            "published_at": None,
            "searchable_at": None,
            "latency_ms": None,
            "status": "placeholder",
        }
        for number in range(1, UPDATE_COUNT + 1)
    ]


def run(events_path: Path | None = None) -> dict[str, Any]:
    measured = events_path is not None
    events = load_events(events_path) if events_path else placeholder_events()
    latencies = (
        [float(event["latency_ms"]) for event in events]
        if measured
        else []
    )
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)

    report = build_stub_report("embedding", ("embedding-suz-recall",))
    report["report_id"] = report["report_id"].replace(
        "embedding-",
        "index-latency-",
        1,
    )
    report["runner_status"] = "ready" if measured else "stub"
    report["requirements"] = [REQUIREMENT]
    report["metrics"]["latency_ms"] = {
        "p50": round(p50, 2),
        "p95": round(p95, 2),
        "status": "measured" if measured else "placeholder",
    }
    report["suite_details"] = {
        "test_type": "incremental_index_latency",
        "target_index": "cc_production",
        "simulated_updates_per_day": UPDATE_COUNT,
        "measured_event_count": len(events) if measured else 0,
        "measurement": "published_at_to_searchable_at",
        "acceptance_limit_ms": ACCEPTANCE_LIMIT_MS,
        "acceptance_target_passed": (
            p95 <= ACCEPTANCE_LIMIT_MS if measured else None
        ),
        "operational_target_p95_ms": OPERATIONAL_TARGET_P95_MS,
        "operational_target_passed": (
            p95 <= OPERATIONAL_TARGET_P95_MS if measured else None
        ),
        "events": events,
        "note": (
            "Measured timestamps must include Celery enqueue, processing, "
            "vector-store commit, and successful search visibility."
        ),
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure incremental-index time to searchable.",
    )
    parser.add_argument(
        "--events",
        type=Path,
        help="JSON with exactly 30 measured update events.",
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
    report = run(args.events)
    report_path = write_report(report, args.output)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
