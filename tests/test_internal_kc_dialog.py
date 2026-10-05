import json
import os
import sys
from pathlib import Path


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
from orchestrator.test_dialog import run_test_prompt  # noqa: E402


class InternalKcTestDialogApiTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"ikc-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_stub_prompt_returns_relevance(self):
        result = run_test_prompt(
            "А какие документы нужны для открытия вклада?",
            scenario_id="CC-SCR-008",
            use_pipeline=False,
        )
        self.assertEqual(result["relevance_percent"], 89)
        self.assertEqual(result["relevance_tone"], "success")
        self.assertIn("паспорт", result["llm_text"].casefold())
        self.assertTrue(result["sources"])

    def test_internal_user_can_post_test_dialog(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_internal_user"))
        response = client.post(
            "/api/v1/sufler/test-dialog",
            data=json.dumps(
                {
                    "text": "Какой срок вклада Стройсбережения?",
                    "scenario_id": "CC-SCR-008",
                    "use_pipeline": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["relevance_percent"], 91)
        self.assertEqual(body["prompt_profile"], "sufler_cc")
        self.assertIn("%", f"{body['relevance_percent']}%")

    def test_operator_forbidden(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.post(
            "/api/v1/sufler/test-dialog",
            data=json.dumps({"text": "тест", "use_pipeline": False}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))
