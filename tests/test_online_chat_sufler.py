import os
import sys
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402


class OnlineChatSuggestApiTest(TestCase):
    """Chat ARM uses the same POST /api/v1/sufler/suggest as telephony (P4-01)."""

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"chat-arm-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_chat_operator_can_request_suggest(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_online_chat_operator")
        )
        fake = {
            "query": "лимит снятия",
            "profile": "sufler_cc",
            "kb_id": "cc_production",
            "hints": [
                {
                    "rank": 1,
                    "text": "Лимит 2000 BYN",
                    "relevance_score": 0.94,
                    "relevance_percent": 94,
                    "citations": [],
                }
            ],
            "citations_enabled": True,
            "blocked_reason": None,
            "min_relevance": 0.7,
            "latency_ms": {"qu": 1, "rag": 1, "llm": 1, "total": 3},
            "request_id": "chat-arm-test",
        }
        with patch("orchestrator.views.suggest", return_value=fake):
            response = client.post(
                "/api/v1/sufler/suggest",
                data='{"text":"Подскажите лимит снятия наличных в банкомате?","limit":5}',
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["hints"][0]["relevance_percent"], 94)
        self.assertEqual(body["request_id"], "chat-arm-test")
