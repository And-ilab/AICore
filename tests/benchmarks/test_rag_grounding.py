import copy
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.rag_grounding import (
    DEFAULT_DATASET_PATH,
    build_stub_predictions,
    evaluate_predictions,
    load_dataset,
    main,
    run,
)


class RagGroundingBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.samples = load_dataset(DEFAULT_DATASET_PATH)

    def test_dataset_has_known_source_chunk_ids(self):
        self.assertEqual(len(self.samples), 10)
        for sample in self.samples:
            self.assertTrue(sample["expected"]["source_chunk_ids"])

    def test_stub_contract_has_placeholder_accuracy(self):
        report = run()
        grounding = report["suite_details"]["citation_accuracy"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertFalse(report["suite_details"]["kpi_evidence"])
        self.assertEqual(grounding["citation_accuracy_percent"], 100.0)
        self.assertEqual(
            report["metrics"]["accuracy_percent"]["status"],
            "placeholder",
        )

    def test_wrong_chunk_id_fails_exact_match(self):
        predictions = build_stub_predictions(self.samples)
        predictions = copy.deepcopy(predictions)
        predictions[0]["citations"][0]["chunk_id"] = (
            "SUZ-UNRELATED#chunk-9999"
        )

        evaluation = evaluate_predictions(self.samples, predictions)

        self.assertEqual(evaluation["citation_accuracy_percent"], 90.0)
        self.assertEqual(evaluation["exact_match_count"], 9)
        self.assertEqual(evaluation["invalid_citation_count"], 1)
        self.assertEqual(evaluation["expected_citation_count"], 10)

    def test_duplicate_citation_fails_exact_match(self):
        predictions = build_stub_predictions(self.samples)
        predictions = copy.deepcopy(predictions)
        predictions[0]["citations"].append(
            copy.deepcopy(predictions[0]["citations"][0])
        )

        evaluation = evaluate_predictions(self.samples, predictions)

        self.assertEqual(evaluation["citation_accuracy_percent"], 90.0)
        self.assertEqual(evaluation["duplicate_citation_count"], 1)

    def test_cli_writes_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--output", str(output)])
            reports = list(output.glob("rag-grounding-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["requirements"], ["FR-LLM-05"])


if __name__ == "__main__":
    unittest.main()
