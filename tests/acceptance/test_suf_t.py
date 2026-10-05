"""SUF-T acceptance harness (P0-04). Smoke: SUF-T-01, SUF-T-04."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import TestCase  # noqa: E402

from tests.acceptance.fixtures import (  # noqa: E402
    api_client_for,
    post_json,
    seed_cc_chunk,
)
from tests.acceptance.harness import (  # noqa: E402
    expand_ids_for,
    mark_acceptance,
    smoke_ids_for,
)


class SufTSmokeAcceptanceTest(TestCase):
    """Foundation smoke: arrange mock RAG → call suggest / widget APIs."""

    @mark_acceptance("SUF-T-01")
    def test_suf_t_01_telephony_hints_after_client_utterance(self):
        """Oktell path: operator gets ranked hints with %% after client text."""
        query = "как оформить дебетовую карту"
        seed_cc_chunk(
            article_id=901,
            title="Оформление дебетовой карты",
            content=query,
        )
        client = api_client_for(
            "contact_center_telephony_operator",
            prefix="suf-t-01",
        )
        response = post_json(
            client,
            "/api/v1/sufler/suggest",
            {"text": query, "limit": 3},
            HTTP_X_REQUEST_ID="suf-t-01",
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["kb_id"], "cc_production")
        self.assertGreaterEqual(len(body["hints"]), 1)
        self.assertLessEqual(len(body["hints"]), 3)
        hint = body["hints"][0]
        self.assertIn("text", hint)
        self.assertTrue(hint.get("citations"))
        self.assertIn("title", hint["citations"][0])
        self.assertIn("latency_ms", body)
        self.assertLessEqual(float(body["latency_ms"].get("total", 0)), 2000.0)

    @mark_acceptance("SUF-T-04")
    def test_suf_t_04_client_channel_has_no_suz_url(self):
        """Client widget reply must not expose SUZ/Bitrix permalinks."""
        from integrations.channels.webhooks import reset_inbox

        reset_inbox()
        query = "лимит снятия наличных"
        seed_cc_chunk(
            article_id=904,
            title="Лимиты снятия",
            content=query,
            permalink="https://suz.bank.local/articles/904",
        )
        # Operator path keeps citations (control).
        operator = api_client_for(
            "contact_center_online_chat_operator",
            prefix="suf-t-04-op",
        )
        suggest = post_json(
            operator,
            "/api/v1/sufler/suggest",
            {"text": query, "limit": 3},
        )
        self.assertEqual(suggest.status_code, 200)
        citations = suggest.json()["hints"][0]["citations"]
        self.assertTrue(
            any("suz" in (c.get("permalink") or "").lower() for c in citations)
        )

        # Client widget reply — no SUZ URL.
        from django.test import Client

        widget = Client()
        response = post_json(
            widget,
            "/api/v1/channels/widget/site-belarusbank/messages/",
            {
                "text": query,
                "placement": "website",
                "locale": "ru",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        reply = str(body.get("reply") or "")
        lowered = reply.lower()
        self.assertNotIn("suz.", lowered)
        self.assertNotIn("bitrix", lowered)
        self.assertNotIn("https://", lowered)
        self.assertTrue(body.get("ok"))


class SufTExpandAcceptanceTest(TestCase):
    def test_expand_ids_are_registered(self):
        smoke = set(smoke_ids_for("sufler"))
        self.assertEqual(smoke, {"SUF-T-01", "SUF-T-04"})
        expand = expand_ids_for("sufler")
        self.assertTrue(expand)
        self.skipTest(
            "P0-04 expand: implement remaining SUF-T-* per "
            "tests/acceptance/EXPAND.md"
        )


if __name__ == "__main__":
    unittest.main()
