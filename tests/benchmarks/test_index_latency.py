import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from benchmarks.suites.index_latency import (
    ACCEPTANCE_LIMIT_MS,
    OPERATIONAL_TARGET_P95_MS,
    UPDATE_COUNT,
    IndexLatencyInputError,
    load_events,
    run,
)


def write_events(path: Path, latency_ms: int) -> None:
    published_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
    events = [
        {
            "article_id": f"article-{number:03d}",
            "published_at": published_at.isoformat(),
            "searchable_at": (
                published_at + timedelta(milliseconds=latency_ms)
            ).isoformat(),
        }
        for number in range(1, UPDATE_COUNT + 1)
    ]
    path.write_text(json.dumps({"events": events}), encoding="utf-8")


class IndexLatencyBenchmarkTest(unittest.TestCase):
    def test_stub_contains_thirty_placeholder_updates(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["simulated_updates_per_day"], 30)
        self.assertEqual(len(details["events"]), 30)
        self.assertIsNone(details["acceptance_target_passed"])
        self.assertEqual(
            report["metrics"]["latency_ms"]["status"],
            "placeholder",
        )

    def test_acceptance_boundary_of_two_minutes_passes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            events_path = Path(temporary_directory) / "events.json"
            write_events(events_path, ACCEPTANCE_LIMIT_MS)
            report = run(events_path)

        details = report["suite_details"]
        self.assertEqual(
            report["metrics"]["latency_ms"]["p95"],
            ACCEPTANCE_LIMIT_MS,
        )
        self.assertTrue(details["acceptance_target_passed"])
        self.assertFalse(details["operational_target_passed"])

    def test_operational_boundary_of_thirty_seconds_passes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            events_path = Path(temporary_directory) / "events.json"
            write_events(events_path, OPERATIONAL_TARGET_P95_MS)
            report = run(events_path)

        self.assertTrue(
            report["suite_details"]["operational_target_passed"]
        )

    def test_rejects_timestamp_without_timezone(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            events_path = Path(temporary_directory) / "events.json"
            write_events(events_path, 1000)
            payload = json.loads(events_path.read_text(encoding="utf-8"))
            payload["events"][0]["published_at"] = "2026-07-20T12:00:00"
            events_path.write_text(
                json.dumps(payload),
                encoding="utf-8",
            )

            with self.assertRaises(IndexLatencyInputError):
                load_events(events_path)


if __name__ == "__main__":
    unittest.main()
