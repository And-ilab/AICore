"""ASS-T acceptance harness (P0-04). Smoke: ASS-T-01, ASS-T-04."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import Client, TestCase  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from tests.acceptance.fixtures import (  # noqa: E402
    api_client_for,
    parse_sse_content,
    post_json,
    user_for_role,
)
from tests.acceptance.harness import (  # noqa: E402
    expand_ids_for,
    mark_acceptance,
    smoke_ids_for,
)


class AssTSmokeAcceptanceTest(TestCase):
    @mark_acceptance("ASS-T-01")
    def test_ass_t_01_assistant_user_login_and_chat(self):
        """AD-mapped assistant user can login session and call chat API."""
        role = ROLES_BY_CODE["ai_assistant_user"]
        user = user_for_role("ai_assistant_user", prefix="ass-t-01")
        # Mirror C2 / mock group membership (I.10 / ASS-T-01).
        self.assertTrue(
            user.groups.filter(name=role.mock_ad_group).exists()
            or user.groups.filter(name=role.c2_ad_group).exists()
        )

        client = Client()
        with patch("auth.views.authenticate", return_value=user):
            # Django login needs backend attr when multiple backends exist.
            user.backend = "django.contrib.auth.backends.ModelBackend"
            login = post_json(
                client,
                "/api/auth/login/",
                {"username": user.username, "password": "ad-password"},
            )
        self.assertEqual(login.status_code, 200, login.content)
        body = login.json()
        self.assertTrue(body["ok"])
        self.assertTrue(body["authenticated"])
        self.assertIn("ai_assistant_user", body["roles"])

        me = client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertTrue(me.json()["authenticated"])

        chat = post_json(
            client,
            "/api/v1/assistant/chat",
            {
                "message": "Нужна справка о вкладе",
                "session_id": "ass-t-01",
                "stream": True,
            },
        )
        self.assertEqual(chat.status_code, 200)
        self.assertIn("text/event-stream", chat["Content-Type"])

    @mark_acceptance("ASS-T-04")
    def test_ass_t_04_pdf_attachment_summarization(self):
        """PDF attachment text is summarized via assistant chat (UC-ASS-04)."""
        client = api_client_for("ai_assistant_user", prefix="ass-t-04")
        response = post_json(
            client,
            "/api/v1/assistant/chat",
            {
                "message": "Сделай краткое саммари документа",
                "session_id": "ass-t-04-pdf",
                "stream": True,
                "attachments": [
                    {
                        "type": "pdf",
                        "name": "policy.pdf",
                        "text": (
                            "Политика банка: клиент может открыть вклад "
                            "онлайн при наличии паспорта."
                        ),
                    }
                ],
            },
        )
        self.assertEqual(response.status_code, 200)
        content, done = parse_sse_content(b"".join(response.streaming_content))
        self.assertTrue(done)
        self.assertTrue(content.strip())


class AssTExpandAcceptanceTest(TestCase):
    def test_expand_ids_are_registered(self):
        smoke = set(smoke_ids_for("assistant"))
        self.assertTrue({"ASS-T-01", "ASS-T-04"} <= smoke)
        self.assertTrue(expand_ids_for("assistant"))
        self.skipTest(
            "P0-04 expand: implement remaining ASS-T-* per "
            "tests/acceptance/EXPAND.md"
        )


if __name__ == "__main__":
    unittest.main()
