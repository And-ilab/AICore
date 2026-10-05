import json
import os
import sys
import tempfile
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
from hub.models import ModelRegistrySettings  # noqa: E402


class ModelRegistryAdminIntegrationTest(TestCase):
    url = "/api/admin/model-registry/model-params/"

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"test-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    @staticmethod
    def payload(**overrides):
        payload = {
            "generation": {
                "temperature": 0.4,
                "top_p": 0.92,
                "max_tokens": 1536,
                "response_chars_max": 480,
                "preset": "standard",
            },
            "rag": {
                "chunk_size_tokens": 768,
                "chunk_overlap_tokens": 128,
                "context_inclusion": 0.64,
                "deterministic_answer": 0.86,
            },
        }
        for section, values in overrides.items():
            payload[section].update(values)
        return payload

    def test_save_and_load_roundtrip(self):
        client = Client()
        user = self.user_for_role("llm_knowledge_base_administrator")
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            with self.settings(
                AUDIT_ENABLED=True,
                AUDIT_SINKS=("file",),
                AUDIT_FILE_PATH=audit_path,
            ):
                client.force_login(user)
                response = client.put(
                    f"{self.url}?profile=assistant_bank",
                    data=json.dumps(self.payload()),
                    content_type="application/json",
                )
            audit_events = [
                json.loads(line)
                for line in audit_path.read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["generation"]["temperature"], 0.4)
        self.assertEqual(response.json()["rag"]["chunk_size_tokens"], 768)

        stored = ModelRegistrySettings.objects.get(
            profile="assistant_bank"
        )
        self.assertEqual(stored.max_tokens, 1536)
        self.assertEqual(stored.updated_by, user.username)
        self.assertTrue(
            any(
                event["event_type"]
                == "hub.administration.kb_settings_updated"
                and event["details"]["profile"] == "assistant_bank"
                for event in audit_events
            )
        )

        loaded = client.get(f"{self.url}?profile=assistant_bank")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(loaded.json()["generation"]["top_p"], 0.92)
        self.assertEqual(
            loaded.json()["rag"]["deterministic_answer"],
            0.86,
        )

    def test_validation_errors_are_returned_by_field(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        payload = self.payload(
            rag={
                "chunk_size_tokens": 256,
                "chunk_overlap_tokens": 256,
                "context_inclusion": 0.9,
                "deterministic_answer": 0.8,
            }
        )

        response = client.put(
            f"{self.url}?profile=assistant_bank",
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        details = response.json()["details"]
        self.assertIn("chunk_overlap_tokens", details)
        self.assertIn("deterministic_answer_threshold", details)

    def test_profile_rbac_denies_cross_module_admin(self):
        client = Client()
        client.force_login(
            self.user_for_role("ai_assistant_module_administrator")
        )

        response = client.get(f"{self.url}?profile=sufler_cc")

        self.assertEqual(response.status_code, 403)

    def test_assistant_rejects_max_response_below_ten(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )
        payload = self.payload(generation={"response_chars_max": 9})
        response = client.put(
            f"{self.url}?profile=assistant_bank",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("response_chars_max", response.json()["details"])

    def test_anonymous_request_is_rejected(self):
        response = Client().get(f"{self.url}?profile=assistant_bank")

        self.assertEqual(response.status_code, 401)
