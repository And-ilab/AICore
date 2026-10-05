import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.ocr_extraction import (
    DEFAULT_DATASET_PATH,
    evaluate_predictions,
    load_dataset,
    main,
    run,
)


class OcrExtractionBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.samples = load_dataset(DEFAULT_DATASET_PATH)

    def _perfect_predictions(self):
        return [
            {
                "id": sample["id"],
                "document_type": sample["expected"]["document_type"],
                "fields": {
                    field: f"value-{field}"
                    for field in sample["expected"]["fields"]
                },
            }
            for sample in self.samples
        ]

    def test_stub_reports_zero_placeholder_by_document_type(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(
            details["acceptance_tests"],
            ["DOC-T-01", "DOC-T-03", "DOC-T-04"],
        )
        self.assertEqual(details["field_accuracy_percent"], 0.0)
        self.assertEqual(len(details["by_document_type"]), 5)
        for metrics in details["by_document_type"].values():
            self.assertEqual(metrics["field_accuracy_percent"], 0.0)
        self.assertEqual(
            report["metrics"]["accuracy_percent"]["status"],
            "placeholder",
        )

    def test_candidate_predictions_score_per_document_type(self):
        evaluation = evaluate_predictions(
            self.samples,
            self._perfect_predictions(),
        )

        self.assertEqual(evaluation["field_accuracy_percent"], 100.0)
        self.assertEqual(evaluation["field_precision_percent"], 100.0)
        self.assertEqual(
            evaluation["document_type_accuracy_percent"],
            100.0,
        )
        for metrics in evaluation["by_document_type"].values():
            self.assertEqual(metrics["field_accuracy_percent"], 100.0)

    def test_false_and_zero_are_valid_extracted_values(self):
        sample = self.samples[3]
        predictions = [
            {
                "id": sample["id"],
                "document_type": sample["expected"]["document_type"],
                "fields": {
                    field: False if field == "signature_present" else 0
                    for field in sample["expected"]["fields"]
                },
            }
        ]

        evaluation = evaluate_predictions([sample], predictions)

        self.assertEqual(evaluation["field_accuracy_percent"], 100.0)

    def test_cli_writes_json_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--output", str(output)])
            reports = list(output.glob("ocr-extraction-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(
                payload["suite_details"]["test_type"],
                "ocr_extraction",
            )


if __name__ == "__main__":
    unittest.main()
