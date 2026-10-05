import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.chunk_grid import (
    CHUNK_OVERLAPS,
    CHUNK_SIZES,
    run,
    select_best,
    write_optimal_defaults,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = (
    REPOSITORY_ROOT / "backend" / "config" / "model_registry.yaml"
)


class ChunkGridBenchmarkTest(unittest.TestCase):
    def test_stub_contains_complete_three_by_three_grid(self):
        report = run()
        details = report["suite_details"]

        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(len(details["grid"]), 9)
        self.assertIsNone(details["best_combination"])
        self.assertEqual(
            {
                (
                    row["chunk_size_tokens"],
                    row["overlap_tokens"],
                )
                for row in details["grid"]
            },
            {
                (chunk_size, overlap)
                for chunk_size in CHUNK_SIZES
                for overlap in CHUNK_OVERLAPS
            },
        )

    def test_select_best_uses_documented_tie_break(self):
        best = select_best(
            [
                {
                    "chunk_size_tokens": 512,
                    "overlap_tokens": 100,
                    "recall_at_5_percent": 90.0,
                },
                {
                    "chunk_size_tokens": 1024,
                    "overlap_tokens": 50,
                    "recall_at_5_percent": 90.0,
                },
            ]
        )

        self.assertEqual(best["chunk_size_tokens"], 1024)
        self.assertEqual(best["overlap_tokens"], 50)

    def test_measured_scores_select_best_and_update_registry(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            scores_path = root / "scores.json"
            scores = [
                {
                    "chunk_size_tokens": chunk_size,
                    "overlap_tokens": overlap,
                    "recall_at_5_percent": (
                        96.0
                        if (chunk_size, overlap) == (512, 100)
                        else 80.0
                    ),
                }
                for chunk_size in CHUNK_SIZES
                for overlap in CHUNK_OVERLAPS
            ]
            scores_path.write_text(
                json.dumps({"scores": scores}),
                encoding="utf-8",
            )
            registry_path = root / "model_registry.yaml"
            registry_path.write_text(
                REGISTRY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            report = run(scores_path)
            best = report["suite_details"]["best_combination"]
            write_optimal_defaults(
                registry_path,
                best,
                benchmark_report="reports/chunk-grid-test.json",
                sign_off="TEST-SIGN-OFF",
            )
            registry = registry_path.read_text(encoding="utf-8")

        self.assertEqual(report["runner_status"], "ready")
        self.assertEqual(best["chunk_size_tokens"], 512)
        self.assertEqual(best["overlap_tokens"], 100)
        self.assertIn("# FR-LLM-03, P1-24:", registry)
        self.assertIn("optimal_chunk_size_tokens: 512", registry)
        self.assertIn("optimal_chunk_overlap_tokens: 100", registry)
        self.assertIn("chunk_selection_status: dev_frozen", registry)
        self.assertIn("last_sign_off: \"TEST-SIGN-OFF\"", registry)


if __name__ == "__main__":
    unittest.main()
