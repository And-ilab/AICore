import json
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
from core.model_gateway import ModelGateway  # noqa: E402
from hub.models import SuflerPolicy  # noqa: E402
from hub.sufler_policy import update_sufler_policy  # noqa: E402
from orchestrator.sufler import suggest  # noqa: E402


def fake_doc(article_id: int, score: float, title: str = "Оформление карты") -> dict:
    return {
        "article_id": article_id,
        "chunk_index": 0,
        "title": title,
        "content": "Оформите карту в отделении с паспортом.",
        "snippet": "Оформите карту в отделении с паспортом.",
        "permalink": f"https://suz.local/articles/{article_id}",
        "relevance_score": score,
        "relevance_percent": int(round(score * 100)),
    }


class SuflerPoliciesApiTest(TestCase):
    url = "/api/admin/sufler/policies/"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"sufler-policy-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_get_returns_defaults(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.get(self.url)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["telephony_min_relevance_percent"], 20)
        self.assertNotIn("chat_min_relevance_percent", body)
        self.assertEqual(body["clarify_min_relevance_percent"], 15)
        self.assertEqual(body["max_hints"], 1)
        self.assertEqual(body["default_mode"], "consultation")
        self.assertEqual(body["model_params_path"], "/ai-hub/admin/model_params/cc")
        self.assertEqual(body["chat_templates_path"], "/online-chat/admin")

    def test_put_roundtrip(self):
        client = Client()
        user = self.user_for_role("contact_center_module_administrator")
        client.force_login(user)
        payload = {
            "telephony_min_relevance_percent": 25,
            "clarify_min_relevance_percent": 20,
            "max_hints": 5,
            "default_mode": "consultation",
        }
        response = client.put(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["telephony_min_relevance_percent"], 25)
        self.assertEqual(body["max_hints"], 5)
        stored = SuflerPolicy.objects.get(pk=1)
        self.assertEqual(stored.updated_by, user.username)
        loaded = client.get(self.url)
        self.assertEqual(loaded.json()["clarify_min_relevance_percent"], 20)

    def test_clarify_above_min_is_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("software_administrator")
        )
        response = client.put(
            self.url,
            data=json.dumps(
                {
                    "telephony_min_relevance_percent": 20,
                    "clarify_min_relevance_percent": 40,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "validation_error")
        self.assertIn(
            "clarify_min_relevance_percent",
            response.json()["details"],
        )

    def test_max_hints_above_five_rejected(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        response = client.put(
            self.url,
            data=json.dumps({"max_hints": 6}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("max_hints", response.json()["details"])

    def test_ocr_admin_is_forbidden(self):
        client = Client()
        client.force_login(
            self.user_for_role("document_recognition_module_administrator")
        )
        response = client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_request_is_rejected(self):
        response = Client().get(self.url)
        self.assertEqual(response.status_code, 401)


class SuflerPolicySuggestTest(TestCase):
    def setUp(self):
        env = patch.dict(
            os.environ,
            {
                "SUFLER_ALLOW_UNGROUNDED": "0",
                "SUFLER_LLM_BASE_URL": "",
                "MODEL_GATEWAY_MODE": "stub",
                "OPENAI_BASE_URL": "",
                "EMBEDDING_MODE": "stub",
            },
            clear=False,
        )
        env.start()
        self.addCleanup(env.stop)

    def test_document_below_threshold_is_dropped(self):
        update_sufler_policy(
            {
                "telephony_min_relevance_percent": 80,
                "clarify_min_relevance_percent": 10,
            }
        )
        retrieved = ({"documents": [fake_doc(11, 0.45)]}, "cc_production")
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=retrieved,
        ):
            with patch(
                "orchestrator.sufler.ModelGateway.chat",
                side_effect=AssertionError("LLM must not be called"),
            ):
                result = suggest(
                    "как оформить карту",
                    limit=2,
                    gateway=ModelGateway.from_registry(),
                    channel="telephony",
                )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "no_relevant_knowledge")
        self.assertEqual(result["min_relevance"], 0.8)

    def test_document_at_threshold_is_kept(self):
        update_sufler_policy({"telephony_min_relevance_percent": 20})
        retrieved = ({"documents": [fake_doc(11, 0.20)]}, "cc_production")
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=retrieved,
        ):
            result = suggest(
                "как оформить карту",
                limit=1,
                gateway=ModelGateway.from_registry(),
                channel="telephony",
            )
        self.assertTrue(result["hints"])
        self.assertIsNone(result["blocked_reason"])

    def test_max_hints_caps_output(self):
        update_sufler_policy({"max_hints": 1})
        retrieved = (
            {
                "documents": [
                    fake_doc(11, 0.92, "Карта"),
                    fake_doc(22, 0.88, "Счёт"),
                ]
            },
            "cc_production",
        )
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=retrieved,
        ):
            result = suggest(
                "как оформить карту",
                limit=2,
                gateway=ModelGateway.from_registry(),
            )
        self.assertEqual(len(result["hints"]), 1)

    def test_service_mode_returns_empty_hints(self):
        with patch(
            "orchestrator.sufler._retrieve_documents",
            side_effect=AssertionError("QU must not run in service mode"),
        ):
            result = suggest(
                "как оформить карту",
                limit=2,
                gateway=ModelGateway.from_registry(),
                mode="service",
            )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "service_mode")

    def test_default_service_mode_blocks_without_request_mode(self):
        update_sufler_policy({"default_mode": SuflerPolicy.MODE_SERVICE})
        result = suggest(
            "как оформить карту",
            limit=2,
            gateway=ModelGateway.from_registry(),
        )
        self.assertEqual(result["hints"], [])
        self.assertEqual(result["blocked_reason"], "service_mode")

    def test_same_threshold_for_chat_and_telephony(self):
        update_sufler_policy(
            {
                "telephony_min_relevance_percent": 80,
                "clarify_min_relevance_percent": 10,
            }
        )
        retrieved = ({"documents": [fake_doc(11, 0.45)]}, "cc_production")
        with patch(
            "orchestrator.sufler._retrieve_documents",
            return_value=retrieved,
        ):
            with patch(
                "orchestrator.sufler.ModelGateway.chat",
                side_effect=AssertionError("LLM must not be called"),
            ):
                chat = suggest(
                    "как оформить карту",
                    limit=2,
                    gateway=ModelGateway.from_registry(),
                    channel="online_chat",
                )
                phone = suggest(
                    "как оформить карту",
                    limit=2,
                    gateway=ModelGateway.from_registry(),
                    channel="telephony",
                )
        self.assertEqual(chat["hints"], [])
        self.assertEqual(phone["hints"], [])
        self.assertEqual(chat["min_relevance"], 0.8)
        self.assertEqual(phone["min_relevance"], 0.8)
