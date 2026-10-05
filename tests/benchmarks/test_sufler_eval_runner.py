import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmarks.suites.sufler_eval import (
    EvaluationInputError,
    main,
    render_markdown,
    run,
    write_reports,
)


class FakeAdapters:
    def classify(self, text):
        return "no_hint.greeting" if text == "здравствуйте" else None

    def scenario(self, case):
        if case["id"] == "SC-T":
            return {"code": "CC-SCR-001", "node_id": "start", "path": ["Старт"]}
        return None

    def retrieve(self, text):
        if text == "где iban":
            return {
                "documents": [
                    {
                        "article_id": 18,
                        "title": "Номер счёта в формате IBAN",
                        "permalink": "suz://accounts/iban",
                    }
                ]
            }
        return {"documents": []}

    def suggest(self, case):
        if case["id"] == "NH-T":
            return {
                "blocked_reason": "no_hint_needed",
                "scenario": None,
                "hints": [],
                "latency_ms": {"total": 0.1},
                "request_id": "nh",
            }
        if case["id"] == "SC-T":
            return {
                "blocked_reason": None,
                "scenario": {"code": "CC-SCR-001", "node_id": "start"},
                "hints": [{"text": "Уточните вид счёта.", "citations": []}],
                "latency_ms": {"total": 0.2},
                "request_id": "sc",
            }
        return {
            "blocked_reason": None,
            "scenario": None,
            "hints": [
                {
                    "text": "IBAN указан в реквизитах счёта.",
                    "citations": [
                        {
                            "article_id": 18,
                            "title": "Номер счёта в формате IBAN",
                            "permalink": "suz://accounts/iban",
                        }
                    ],
                }
            ],
            "latency_ms": {"total": 0.3},
            "request_id": "kb",
        }


def fixture_dataset(path):
    payload = {
        "schema_version": "1.0",
        "id": "runner-fixture",
        "version": "1.0.0",
        "samples": [
            {
                "id": "NH-T",
                "version": "1.0.0",
                "bucket": "no_hint",
                "case_type": "phatic",
                "input": {"text": "здравствуйте", "language": "ru"},
                "expected": {
                    "route": "no_hint",
                    "classification": "no_hint.greeting",
                },
            },
            {
                "id": "SC-T",
                "version": "1.0.0",
                "bucket": "scenario",
                "case_type": "start",
                "input": {"text": "открыть счёт", "language": "ru"},
                "expected": {
                    "route": "scenario",
                    "scenario_code": "CC-SCR-001",
                    "node_id": "start",
                },
            },
            {
                "id": "KB-T",
                "version": "1.0.0",
                "bucket": "kb",
                "case_type": "banking_question",
                "input": {"text": "где iban", "language": "ru"},
                "expected": {
                    "route": "knowledge_base",
                    "source_titles": ["Номер счёта в формате IBAN"],
                    "required_concepts": ["IBAN"],
                },
            },
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class SuflerEvaluationRunnerTest(unittest.TestCase):
    def test_all_layers_record_expected_actual_routing_and_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_path = Path(temporary_directory) / "dataset.json"
            fixture_dataset(dataset_path)
            ticks = iter(index / 1000 for index in range(100))

            report = run(
                dataset_path=dataset_path,
                adapters=FakeAdapters(),
                clock=lambda: next(ticks),
            )

        self.assertEqual(len(report["results"]), 6)
        self.assertEqual(set(report["metrics"]["layers"]), {
            "classification",
            "scenario",
            "retrieval",
            "full_suggest",
        })
        self.assertEqual(
            {
                layer: metrics["cases"]
                for layer, metrics in report["metrics"]["layers"].items()
            },
            {
                "classification": 1,
                "scenario": 1,
                "retrieval": 1,
                "full_suggest": 3,
            },
        )
        full_kb = next(
            item
            for item in report["results"]
            if item["id"] == "KB-T" and item["layer"] == "full_suggest"
        )
        self.assertTrue(full_kb["passed"])
        self.assertEqual(full_kb["actual"]["routing"], "knowledge_base")
        self.assertEqual(full_kb["actual"]["citations"][0]["article_id"], 18)
        self.assertIn("pipeline_latency_ms", full_kb["actual"])
        self.assertIn("expected", full_kb)
        self.assertIn("actual", full_kb)

    def test_writes_matching_json_and_markdown_reports(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            dataset_path = root / "dataset.json"
            fixture_dataset(dataset_path)
            report = run(
                dataset_path=dataset_path,
                layers=("classification",),
                adapters=FakeAdapters(),
            )
            json_path, markdown_path = write_reports(report, root / "reports")

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertEqual(
                json.loads(json_path.read_text(encoding="utf-8"))["report_id"],
                report["report_id"],
            )
            markdown = markdown_path.read_text(encoding="utf-8")
            self.assertEqual(markdown, render_markdown(report))
            self.assertIn("| classification |", markdown)

    def test_cli_requires_explicit_live_llm_opt_in(self):
        with self.assertRaisesRegex(EvaluationInputError, "allow-live-llm"):
            main(["--gateway-mode", "openai"])

    def test_fake_runner_has_no_network_dependency(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            dataset_path = Path(temporary_directory) / "dataset.json"
            fixture_dataset(dataset_path)
            with patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("network access is forbidden"),
            ):
                report = run(
                    dataset_path=dataset_path,
                    adapters=FakeAdapters(),
                )
        self.assertEqual(report["dataset"]["case_count"], 3)


if __name__ == "__main__":
    unittest.main()
