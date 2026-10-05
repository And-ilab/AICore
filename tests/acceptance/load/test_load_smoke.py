"""Smoke: II.7.4 load runner subprocess meets p95 target at reduced scale."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RUN_LOAD = REPOSITORY_ROOT / "tests" / "acceptance" / "load" / "run_load.py"
STATS = REPOSITORY_ROOT / "tests" / "acceptance" / "load" / "last_stats.json"


class LoadRunnerSmokeTest(unittest.TestCase):
    def test_pipeline_load_subprocess_meets_p95(self):
        # Subprocess so gevent.monkey.patch_all runs before Django setup.
        completed = subprocess.run(
            [
                sys.executable,
                str(RUN_LOAD),
                "--users",
                "10",
                "--duration",
                "5",
                "--spawn-rate",
                "10",
            ],
            cwd=str(REPOSITORY_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            msg=completed.stdout + "\n" + completed.stderr,
        )
        stats = json.loads(STATS.read_text(encoding="utf-8"))
        self.assertGreater(stats["requests"], 0)
        self.assertEqual(stats["failures"], 0)
        self.assertLessEqual(stats["latency_ms"]["p95"], 2000)
        self.assertTrue(stats["pass"])


if __name__ == "__main__":
    unittest.main()
