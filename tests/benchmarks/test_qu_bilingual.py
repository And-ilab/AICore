import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.qu_bilingual import load_dataset, run


def write_predictions(
    path: Path,
    *,
    wrong_en_id: str | None = None,
) -> None:
    predictions = []
    for sample in load_dataset():
        expected = sample["expected_intent_id"]
        en_intent = (
            "CC-SCR-999"
            if sample["id"] == wrong_en_id
            else expected
        )
        predictions.append(
            {
                "id": sample["id"],
                "ru": {
                    "matched": True,
                    "intent_id": expected,
                    "relevance_score": 0.92,
                },
                "en": {
                    "matched": True,
                    "intent_id": en_intent,
                    "relevance_score": 0.88,
                },
            }
        )
    path.write_text(
        json.dumps({"predictions": predictions}),
        encoding="utf-8",
    )


class QuBilingualBenchmarkTest(unittest.TestCase):
    def test_dataset_contains_ten_same_intent_pairs(self):
        samples = load_dataset()

        self.assertEqual(len(samples), 10)
        self.assertTrue(
            all(
                sample["source_scenario_id"]
                == sample["expected_intent_id"]
                for sample in samples
            )
        )

    def test_stub_report_has_placeholder_match_rates(self):
        report = run()

        self.assertEqual(report["runner_status"], "stub")
        self.assertIsNone(report["suite_details"]["overall_passed"])
        self.assertTrue(
            all(
                rate is None
                for rate in report["suite_details"]["match_rates"].values()
            )
        )

    def test_perfect_bilingual_predictions_are_green(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            predictions_path = Path(temporary_directory) / "predictions.json"
            write_predictions(predictions_path)
            report = run(predictions_path)

        rates = report["suite_details"]["match_rates"]
        self.assertTrue(report["suite_details"]["overall_passed"])
        self.assertEqual(rates["ru_match_rate_percent"], 100)
        self.assertEqual(rates["en_match_rate_percent"], 100)
        self.assertEqual(
            rates["cross_language_consistency_percent"],
            100,
        )
        self.assertEqual(
            report["suite_details"]["acceptance_tests"],
            ["SUF-T-12"],
        )

    def test_wrong_english_intent_reduces_en_and_consistency_rates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            predictions_path = Path(temporary_directory) / "predictions.json"
            write_predictions(
                predictions_path,
                wrong_en_id="QU-BI-001",
            )
            report = run(predictions_path)

        rates = report["suite_details"]["match_rates"]
        self.assertFalse(report["suite_details"]["overall_passed"])
        self.assertEqual(rates["ru_match_rate_percent"], 100)
        self.assertEqual(rates["en_match_rate_percent"], 90)
        self.assertEqual(
            rates["cross_language_consistency_percent"],
            90,
        )


if __name__ == "__main__":
    unittest.main()
