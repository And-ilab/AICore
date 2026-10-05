"""CHAT-T acceptance harness (P0-04). Smoke: CHAT-T-01, CHAT-T-04."""

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

from django.test import Client, TestCase  # noqa: E402

from integrations.channels.webhooks import reset_inbox  # noqa: E402
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


class ChatTSmokeAcceptanceTest(TestCase):
    def setUp(self):
        reset_inbox()

    @mark_acceptance("CHAT-T-01")
    def test_chat_t_01_widget_dialog_reaches_arm_inbox(self):
        """Client starts site dialog → reply + inbox card (entry URL/widget)."""
        client = Client()
        response = post_json(
            client,
            "/api/v1/channels/widget/site-belarusbank/messages/",
            {
                "text": "Здравствуйте, нужна справка",
                "placement": "website",
                "locale": "ru",
                "page_url": "https://belarusbank.by/chat",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["widget_id"], "site-belarusbank")
        self.assertEqual(body["routed_to"], "arm_queue")
        self.assertTrue(body["reply"])

        inbox = client.get("/api/v1/channels/inbox/")
        self.assertEqual(inbox.status_code, 200)
        payload = inbox.json()
        self.assertGreaterEqual(payload["count"], 1)
        card = payload["items"][0]
        self.assertEqual(card["channel"], "widget")
        self.assertIn("Здравствуйте", card["text"])

    @mark_acceptance("CHAT-T-04")
    def test_chat_t_04_arm_sufler_hint_with_article_title(self):
        """ARM sufler hint from SUZ includes article title (↗ citation)."""
        query = "как открыть вклад"
        seed_cc_chunk(
            article_id=940,
            title="Открытие вклада",
            content=query,
        )
        client = api_client_for(
            "contact_center_online_chat_operator",
            prefix="chat-t-04",
        )
        response = post_json(
            client,
            "/api/v1/sufler/suggest",
            {"text": query, "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["kb_id"], "cc_production")
        self.assertGreaterEqual(len(body["hints"]), 1)
        citation = body["hints"][0]["citations"][0]
        self.assertEqual(citation["title"], "Открытие вклада")
        self.assertTrue(citation.get("permalink"))


class ChatTExpandAcceptanceTest(TestCase):
    def test_expand_ids_are_registered(self):
        self.assertEqual(
            set(smoke_ids_for("chat")),
            {"CHAT-T-01", "CHAT-T-04"},
        )
        self.assertTrue(expand_ids_for("chat"))
        self.skipTest(
            "P0-04 expand: implement remaining CHAT-T-* per "
            "tests/acceptance/EXPAND.md"
        )


if __name__ == "__main__":
    unittest.main()
