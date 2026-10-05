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


class HealthEndpointTests(unittest.TestCase):
    """GET /health/ — db + redis probes for TEST/PROD application tier."""

    def test_health_returns_200_with_db_and_redis_keys(self):
        client = Client()
        response = client.get("/health/")
        self.assertEqual(
            response.status_code,
            200,
            msg=response.content.decode(),
        )
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertIn("database", payload["checks"])
        self.assertIn("redis", payload["checks"])
        self.assertEqual(payload["checks"]["database"]["status"], "ok")
        self.assertEqual(payload["checks"]["redis"]["status"], "ok")
        self.assertEqual(payload["asgi"], "daphne")
        self.assertIn("channel_layer", payload)

    def test_health_pings_redis_when_configured(self):
        client = Client()
        fake = mock.MagicMock()
        fake.ping.return_value = True
        with mock.patch.dict(os.environ, {"REDIS_HOST": "redis", "REDIS_PORT": "6379"}):
            with mock.patch("redis.Redis.from_url", return_value=fake) as from_url:
                response = client.get("/health/")
        self.assertEqual(
            response.status_code,
            200,
            msg=response.content.decode(),
        )
        from_url.assert_called()
        payload = response.json()
        self.assertEqual(payload["checks"]["redis"]["status"], "ok")
        self.assertEqual(payload["checks"]["redis"].get("host"), "redis")

    def test_health_degraded_when_database_fails(self):
        client = Client()
        with mock.patch(
            "core.health._check_database",
            return_value={"status": "error", "detail": "boom"},
        ):
            response = client.get("/health/")
        self.assertEqual(response.status_code, 503)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["checks"]["database"]["status"], "error")


if __name__ == "__main__":
    unittest.main()
