import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = REPOSITORY_ROOT / "benchmarks" / "bench.py"


class BenchmarkCliIntegrationTest(unittest.TestCase):
    def test_asr_suite_exits_zero_and_writes_report(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory) / "reports"
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI_PATH),
                    "run",
                    "--suite",
                    "asr",
                    "--output",
                    str(output),
                ],
                cwd=REPOSITORY_ROOT,
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "ASR_BENCH_FORCE_STUB": "1"},
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            reports = list(output.glob("*.json"))
            self.assertEqual(len(reports), 1)

            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], "1.0")
            self.assertEqual(report["suite"], "asr")
            self.assertEqual(report["runner_status"], "stub")
            self.assertIn("p50", report["metrics"]["latency_ms"])
            self.assertIn("p95", report["metrics"]["latency_ms"])
            self.assertIsNone(report["metrics"]["wer_percent"]["value"])
            self.assertIsNone(
                report["metrics"]["accuracy_percent"]["value"]
            )
            self.assertEqual(
                report["requirements"],
                ["FR-ASR-01", "FR-ASR-04", "FR-ASR-07"],
            )


if __name__ == "__main__":
    unittest.main()
