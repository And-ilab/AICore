import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from benchmarks.suites.llm_load import main, run_load_test


class LlmLoadBenchmarkTest(unittest.TestCase):
    def test_dev_stub_completes_without_oom_or_timeout(self):
        report = asyncio.run(
            run_load_test(
                requests_per_second=20,
                duration_seconds=0.1,
                request_timeout_seconds=1,
            )
        )
        details = report["suite_details"]

        self.assertEqual(report["requirements"], ["FR-LLM-07"])
        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["scheduled_requests"], 2)
        self.assertEqual(details["successful_requests"], 2)
        self.assertEqual(details["timeout_count"], 0)
        self.assertEqual(details["oom_count"], 0)
        self.assertTrue(details["completed_without_oom_or_timeout"])
        self.assertTrue(details["completed_without_failures"])
        self.assertFalse(details["fr_llm_07"]["target_met"])
        self.assertFalse(details["fr_llm_07"]["kpi_evidence"])
        self.assertEqual(
            report["metrics"]["latency_ms"]["status"],
            "placeholder",
        )
        self.assertIn("logical_cpu_count", details["hardware"])
        self.assertIn("memory_total_gb", details["hardware"])

    def test_invalid_load_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            asyncio.run(run_load_test(requests_per_second=0))
        with self.assertRaises(ValueError):
            asyncio.run(run_load_test(duration_seconds=0))
        with self.assertRaises(ValueError):
            asyncio.run(run_load_test(request_timeout_seconds=0))

    def test_cli_writes_short_stub_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            exit_code = main(
                [
                    "--mode",
                    "stub",
                    "--rps",
                    "20",
                    "--duration",
                    "0.05",
                    "--output",
                    str(output),
                ]
            )
            reports = list(output.glob("llm-load-*.json"))

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["suite_details"]["scheduled_requests"], 1)


if __name__ == "__main__":
    unittest.main()
