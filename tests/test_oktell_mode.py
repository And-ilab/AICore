"""Unit tests for OKTELL_MODE=mock|prod profile switching (P4-02)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import SimpleTestCase, override_settings  # noqa: E402

from integrations.oktell.client import OktellClient, OktellClientError  # noqa: E402
from integrations.oktell.config import (  # noqa: E402
    resolve_oktell_mode,
    resolve_oktell_profile,
    resolve_oktell_ws_url,
)


class OktellModeFlagTest(SimpleTestCase):
    def test_normalize_aliases(self):
        self.assertEqual(resolve_oktell_mode("mock"), "mock")
        self.assertEqual(resolve_oktell_mode("PROD"), "prod")
        self.assertEqual(resolve_oktell_mode("t45"), "prod")
        self.assertEqual(resolve_oktell_mode("test"), "prod")

    @override_settings(
        OKTELL_MODE="mock",
        OKTELL_MOCK_WS_URL="ws://127.0.0.1:8766",
        OKTELL_WS_URL="ws://ignored-in-favor-of-mock:1",
        OKTELL_ENABLED=True,
    )
    def test_mock_profile_uses_mock_url(self):
        profile = resolve_oktell_profile()
        self.assertEqual(profile.mode, "mock")
        self.assertEqual(profile.profile_id, "oktell_mock")
        self.assertEqual(profile.ws_url, "ws://127.0.0.1:8766")
        self.assertEqual(profile.marking, "DEV_MOCK")
        self.assertEqual(resolve_oktell_ws_url(), "ws://127.0.0.1:8766")

        client = OktellClient.from_settings()
        self.assertEqual(client.mode, "mock")
        self.assertEqual(client.url, "ws://127.0.0.1:8766")
        self.assertEqual(client.describe()["profile_id"], "oktell_mock")

    @override_settings(
        OKTELL_MODE="prod",
        OKTELL_PROD_WS_URL="wss://oktell-test.bank.local/ws",
        OKTELL_WS_URL="wss://fallback.example/ws",
        OKTELL_PROFILE_ID="test_line_t45",
        OKTELL_TEST_QUEUE="Q-TEST-45",
        OKTELL_TEST_MARKING="TEST_OKTELL_T45",
        OKTELL_ENABLED=True,
    )
    def test_prod_profile_uses_t45_test_line(self):
        profile = resolve_oktell_profile()
        self.assertEqual(profile.mode, "prod")
        self.assertEqual(profile.profile_id, "test_line_t45")
        self.assertEqual(profile.ws_url, "wss://oktell-test.bank.local/ws")
        self.assertEqual(profile.queue, "Q-TEST-45")
        self.assertEqual(profile.marking, "TEST_OKTELL_T45")

        client = OktellClient.from_settings()
        self.assertEqual(client.mode, "prod")
        self.assertEqual(client.url, "wss://oktell-test.bank.local/ws")
        description = client.describe()
        self.assertEqual(description["line_label"], "T+45 test line")
        self.assertIn("T+45", description["notes"])

    @override_settings(OKTELL_MODE="prod", OKTELL_PROD_WS_URL="", OKTELL_WS_URL="")
    def test_prod_without_url_raises(self):
        with self.assertRaises(ValueError):
            resolve_oktell_profile()

    @override_settings(
        OKTELL_MODE="prod",
        OKTELL_PROD_WS_URL="wss://oktell-test.bank.local/ws",
    )
    def test_run_lifecycle_blocked_in_prod(self):
        import asyncio

        client = OktellClient.from_settings()

        async def _run():
            with patch.object(client, "connect", return_value=None), patch.object(
                client,
                "subscribe_phoneevents",
                return_value={"result": 1},
            ):
                await client.connect_and_subscribe(run_lifecycle=True)

        with self.assertRaises(OktellClientError):
            asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
