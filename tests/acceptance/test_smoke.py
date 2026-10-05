import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.test import Client  # noqa: E402


class BackendSmokeTest(unittest.TestCase):
    def test_django_check_and_main_gets(self):
        call_command("check", verbosity=0)
        client = Client()
        self.assertEqual(client.get("/").status_code, 302)
        self.assertEqual(client.get("/health/").status_code, 200)
        self.assertEqual(client.get("/client-info/").status_code, 200)
        self.assertEqual(client.get("/chat/").status_code, 302)


if __name__ == "__main__":
    unittest.main()
