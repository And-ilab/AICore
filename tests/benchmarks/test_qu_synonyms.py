import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.qu_synonyms import (
    EXPECTED_CATEGORY_COUNTS,
    load_dataset,
    run,
)


def write_predictions(
    path: Path,
    *,
    wrong_id: str | None = None,
) -> None:
    predictions = []
    for sample in load_dataset():
        matched = sample["expected_match"]
        intent = sample["expected_intent_id"]
        if sample["id"] == wrong_id:
            matched = not matched
            intent = sample["source_scenario_id"] if matched else None
        predictions.append(
            {
                "id": sample["id"],
                "matched": matched,
                "predicted_intent_id": intent,
                "relevance_score": 0.9 if matched else 0.2,
            }
        )
    path.write_text(
        json.dumps({"predictions": predictions}),
        encoding="utf-8",
    )


class QuSynonymsBenchmarkTest(unittest.TestCase):
    def test_dataset_has_expected_category_matrix(self):
        samples = load_dataset()
        counts = {
            category: sum(
                sample["category"] == category for sample in samples
            )
            for category in EXPECTED_CATEGORY_COUNTS
        }

        self.assertEqual(len(samples), 20)
        self.assertEqual(counts, EXPECTED_CATEGORY_COUNTS)

    def test_stub_report_has_placeholder_categories(self):
        report = run()

        self.assertEqual(report["runner_status"], "stub")
        self.assertIsNone(report["suite_details"]["overall_passed"])
        self.assertTrue(
            all(
                result["status"] == "placeholder"
                for result in report["suite_details"]["categories"].values()
            )
        )

    def test_perfect_predictions_pass_all_categories(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            predictions_path = Path(temporary_directory) / "predictions.json"
            write_predictions(predictions_path)
            report = run(predictions_path)

        self.assertTrue(report["suite_details"]["overall_passed"])
        self.assertEqual(report["metrics"]["accuracy_percent"]["value"], 100)
        self.assertTrue(
            all(
                result["status"] == "passed"
                for result in report["suite_details"]["categories"].values()
            )
        )

    def test_incorrect_antonym_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            predictions_path = Path(temporary_directory) / "predictions.json"
            write_predictions(predictions_path, wrong_id="QU-ANT-001")
            report = run(predictions_path)

        antonyms = report["suite_details"]["categories"]["antonyms"]
        self.assertFalse(report["suite_details"]["overall_passed"])
        self.assertEqual(antonyms["failed"], 1)
        self.assertEqual(antonyms["status"], "failed")


if __name__ == "__main__":
    unittest.main()
