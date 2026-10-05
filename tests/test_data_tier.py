import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from io import StringIO  # noqa: E402


class VerifyDataTierCommandTests(unittest.TestCase):
    def test_verify_data_tier_ok_on_sqlite(self):
        out = StringIO()
        call_command("verify_data_tier", stdout=out)
        text = out.getvalue()
        self.assertIn("connection: ok", text)
        self.assertIn("skip pgvector", text)


class DataTierScriptsTests(unittest.TestCase):
    def test_ensure_pgvector_sql_mentions_hnsw(self):
        sql = (ROOT / "infra/test/sql/ensure_pgvector.sql").read_text(encoding="utf-8")
        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector", sql)
        self.assertIn("cc_prod_embedding_hnsw_idx", sql)
        self.assertIn("hnsw", sql)

    def test_backup_stub_dry_run_is_runnable(self):
        script = ROOT / "infra/test/backup-postgres.sh"
        self.assertTrue(script.is_file())
        # Git Bash / WSL / Linux — skip if no bash.
        bash = None
        for candidate in ("bash", "C:\\Program Files\\Git\\bin\\bash.exe"):
            try:
                subprocess.run(
                    [candidate, "-c", "exit 0"],
                    check=True,
                    capture_output=True,
                )
                bash = candidate
                break
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
        if bash is None:
            self.skipTest("bash not available")
        proc = subprocess.run(
            [bash, str(script), "--dry-run"],
            cwd=str(script.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        combined = (proc.stdout or "") + (proc.stderr or "")
        self.assertIn("dry-run", combined.lower())
        self.assertIn("pg_dump", combined)


if __name__ == "__main__":
    unittest.main()
