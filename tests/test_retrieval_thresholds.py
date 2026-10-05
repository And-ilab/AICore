import json
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from rag.thresholds import (  # noqa: E402
    RetrievalThresholdError,
    RetrievalThresholds,
    get_thresholds,
    set_threshold,
    set_thresholds,
)

from benchmarks.suites.retrieval_thresholds import (  # noqa: E402
    calibrate,
    load_labeled_scores,
    run,
)


REGISTRY_PATH = BACKEND_ROOT / "config" / "model_registry.yaml"


class RetrievalThresholdApiTest(unittest.TestCase):
    def test_accepts_boundary_values(self):
        thresholds = RetrievalThresholds(0, 1)

        self.assertEqual(thresholds.context_inclusion, 0)
        self.assertEqual(thresholds.deterministic_answer, 1)

    def test_rejects_out_of_range_boolean_and_reversed_values(self):
        invalid_values = (
            (-0.01, 0.8),
            (0.5, 1.01),
            (True, 0.8),
            (0.9, 0.8),
        )

        for context, deterministic in invalid_values:
            with self.subTest(
                context=context,
                deterministic=deterministic,
            ):
                with self.assertRaises(RetrievalThresholdError):
                    RetrievalThresholds(context, deterministic)

    def test_setters_preserve_registry_and_validate_single_update(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            registry_path = Path(temporary_directory) / "registry.yaml"
            registry_path.write_text(
                REGISTRY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            with self.assertRaises(RetrievalThresholdError):
                set_thresholds(0.7, 0.9, registry_path)

            updated = set_thresholds(
                0.7,
                0.9,
                registry_path,
                benchmark_report="reports/threshold-test.json",
                sign_off="TEST-SIGN-OFF-1",
            )
            updated = set_threshold(
                "deterministic_answer",
                0.95,
                registry_path,
                benchmark_report="reports/threshold-test-2.json",
                sign_off="TEST-SIGN-OFF-2",
            )
            content = registry_path.read_text(encoding="utf-8")

            self.assertEqual(updated.context_inclusion, 0.7)
            self.assertEqual(updated.deterministic_answer, 0.95)
            self.assertEqual(updated.status, "dev_frozen")
            self.assertIn("# FR-LLM-04:", content)
            self.assertEqual(get_thresholds(registry_path), updated)

            with self.assertRaises(RetrievalThresholdError):
                set_threshold(
                    "context_inclusion",
                    0.96,
                    registry_path,
                    benchmark_report="reports/threshold-test-3.json",
                    sign_off="TEST-SIGN-OFF-3",
                )


class RetrievalThresholdCalibrationTest(unittest.TestCase):
    def test_calibrates_context_and_deterministic_thresholds(self):
        samples = [
            {"score": 0.95, "relevant": True, "deterministic_correct": True},
            {"score": 0.90, "relevant": True, "deterministic_correct": True},
            {"score": 0.80, "relevant": True, "deterministic_correct": False},
            {"score": 0.70, "relevant": True, "deterministic_correct": False},
            {"score": 0.55, "relevant": False, "deterministic_correct": False},
            {"score": 0.40, "relevant": False, "deterministic_correct": False},
        ]

        recommended = calibrate(samples)

        self.assertEqual(recommended["context_inclusion"], 0.7)
        self.assertEqual(recommended["deterministic_answer"], 0.9)

    def test_report_uses_measured_labeled_scores(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            registry_path = root / "registry.yaml"
            registry_path.write_text(
                REGISTRY_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            samples_path = root / "samples.json"
            samples_path.write_text(
                json.dumps(
                    {
                        "samples": [
                            {
                                "id": "positive",
                                "score": 0.9,
                                "relevant": True,
                                "deterministic_correct": True,
                            },
                            {
                                "id": "context-only",
                                "score": 0.7,
                                "relevant": True,
                                "deterministic_correct": False,
                            },
                            {
                                "id": "negative",
                                "score": 0.4,
                                "relevant": False,
                                "deterministic_correct": False,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_labeled_scores(samples_path)
            report = run(
                samples_path,
                registry_path=registry_path,
            )

        self.assertEqual(len(loaded), 3)
        self.assertEqual(report["runner_status"], "ready")
        self.assertEqual(report["requirements"], ["FR-LLM-04"])
        self.assertEqual(
            report["suite_details"]["recommended"]["context_inclusion"],
            0.7,
        )
        self.assertEqual(
            report["suite_details"]["recommended"]["deterministic_answer"],
            0.9,
        )


if __name__ == "__main__":
    unittest.main()
