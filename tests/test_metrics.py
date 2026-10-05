import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import Client  # noqa: E402


class MetricsEndpointTests(unittest.TestCase):
    """GET /metrics/ — Prometheus text for TEST observability."""

    def test_metrics_exposes_health_gauges(self):
        client = Client()
        response = client.get("/metrics/")
        self.assertEqual(response.status_code, 200, msg=response.content.decode())
        self.assertIn("text/plain", response["Content-Type"])
        body = response.content.decode()
        self.assertIn("sufler_up 1", body)
        self.assertIn("sufler_health_ok 1", body)
        self.assertIn('sufler_health_check{component="database"} 1', body)
        self.assertIn('sufler_health_check{component="redis"} 1', body)

    def test_metrics_health_ok_zero_when_degraded(self):
        client = Client()
        with mock.patch(
            "core.health._check_database",
            return_value={"status": "error", "detail": "boom"},
        ):
            response = client.get("/metrics/")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("sufler_health_ok 0", body)
        self.assertIn('sufler_health_check{component="database"} 0', body)


class ObservabilityStubTests(unittest.TestCase):
    def test_alert_and_scrape_stubs_exist(self):
        base = ROOT / "infra" / "test" / "observability"
        alerts = (base / "prometheus-alerts.yml").read_text(encoding="utf-8")
        scrape = (base / "prometheus-scrape.yml").read_text(encoding="utf-8")
        readme = (base / "README.md").read_text(encoding="utf-8")
        self.assertIn("SuflerTestHealthFail", alerts)
        self.assertIn("sufler_health_ok", alerts)
        self.assertIn("job_name: sufler-test", scrape)
        self.assertIn("/metrics/", scrape)
        self.assertIn("Structured logging", readme)


if __name__ == "__main__":
    unittest.main()
