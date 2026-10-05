import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.embedding_recall import (
    CANDIDATES,
    EXPECTED_SAMPLE_COUNT,
    load_dataset,
    main,
    run,
)


class EmbeddingRecallBenchmarkTest(unittest.TestCase):
    def test_dataset_contains_twenty_labeled_documents(self):
        samples = load_dataset()

        self.assertEqual(len(samples), EXPECTED_SAMPLE_COUNT)
        self.assertEqual(EXPECTED_SAMPLE_COUNT, 20)
        self.assertEqual(
            len({sample["document"]["id"] for sample in samples}),
            20,
        )

    def test_stub_report_lists_candidate_recall_at_five(self):
        report = run()
        results = report["suite_details"]["candidate_results"]

        self.assertEqual(report["suite"], "embedding")
        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(report["suite_details"]["metric"], "recall@5")
        self.assertEqual(len(results), len(CANDIDATES))
        self.assertTrue(
            all(
                result["recall_at_5_percent"] is None
                and result["status"] == "placeholder"
                for result in results
            )
        )

    def test_cli_exits_zero_and_writes_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(["--output", str(output)])
            reports = list(output.glob("embedding-recall-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["suite_details"]["sample_count"], 20)


if __name__ == "__main__":
    unittest.main()
