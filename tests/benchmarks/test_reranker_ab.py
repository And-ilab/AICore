import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.qu_synonyms import load_dataset
from benchmarks.suites.reranker_ab import (
    compare,
    evaluate_rankings,
    main,
    run,
)


class RerankerAbBenchmarkTest(unittest.TestCase):
    def setUp(self):
        self.samples = load_dataset()

    def _predictions(self, expected_first):
        predictions = {}
        for sample in self.samples:
            expected = sample["expected_intent_id"]
            if sample["expected_match"]:
                ranked_ids = (
                    [expected, "CC-SCR-999"]
                    if expected_first
                    else ["CC-SCR-999", expected]
                )
                matched = True
            else:
                ranked_ids = ["CC-SCR-998", "CC-SCR-999"]
                matched = False
            predictions[sample["id"]] = {
                "id": sample["id"],
                "matched": matched,
                "ranked_results": [
                    {"intent_id": intent_id, "score": 0.9 - rank * 0.1}
                    for rank, intent_id in enumerate(ranked_ids)
                ],
                "latency_ms": 10.0 if expected_first else 2.0,
            }
        return predictions

    def test_default_run_is_non_blocking_skip_without_model(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["status"], "skipped")
        self.assertEqual(
            details["skip_reason"],
            "reranker_model_not_configured",
        )
        self.assertFalse(details["blocking_for_p1_61"])

    def test_ab_metrics_show_quality_improvement(self):
        baseline = evaluate_rankings(
            self.samples,
            self._predictions(expected_first=False),
        )
        reranked = evaluate_rankings(
            self.samples,
            self._predictions(expected_first=True),
        )
        comparison = compare(baseline, reranked)

        self.assertLess(
            baseline["top1_accuracy_percent"],
            reranked["top1_accuracy_percent"],
        )
        self.assertEqual(reranked["top1_accuracy_percent"], 100.0)
        self.assertTrue(comparison["no_quality_regression"])
        self.assertTrue(comparison["quality_improved"])
        self.assertEqual(
            comparison["recommendation"],
            "consider_reranker",
        )

    def test_cli_writes_skipped_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--output", str(output)])
            reports = list(output.glob("reranker-ab-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(
                payload["suite_details"]["status"],
                "skipped",
            )


if __name__ == "__main__":
    unittest.main()
