import asyncio
import unittest

from benchmarks.suites.asr_load import run_load_test


class AsrLoadBenchmarkTest(unittest.TestCase):
    def test_stub_runs_seventy_async_streams_without_failures(self):
        report = asyncio.run(
            run_load_test(stream_count=70, force_stub=True)
        )
        details = report["suite_details"]

        self.assertEqual(report["requirements"], ["FR-ASR-03"])
        self.assertEqual(report["runner_status"], "stub")
        self.assertEqual(details["configured_streams"], 70)
        self.assertEqual(details["successful_streams"], 70)
        self.assertEqual(details["failed_streams"], 0)
        self.assertTrue(details["harness_completed_without_crashes"])
        self.assertFalse(details["fr_asr_03_load_target_met"])
        self.assertEqual(
            report["metrics"]["latency_ms"]["status"],
            "placeholder",
        )
        self.assertIn("logical_cpu_count", details["hardware"])
        self.assertIn("memory_total_gb", details["hardware"])


if __name__ == "__main__":
    unittest.main()
