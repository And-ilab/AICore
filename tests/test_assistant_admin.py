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
from django.core.files.uploadedfile import SimpleUploadedFile  # noqa: E402

from hub.models import AssistantKnowledgeBase  # noqa: E402
from ingest.models import AssistantProductionChunk, CCProductionChunk  # noqa: E402


class AssistantAdminApiTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"asst-admin-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_assistant_kb_namespace_isolated_from_cc_production(self):
        client = Client()
        client.force_login(
            self.user_for_role("ai_assistant_module_administrator")
        )

        listed = client.get("/api/admin/assistant/kb/")
        self.assertEqual(listed.status_code, 200)
        payload = listed.json()
        self.assertEqual(payload["namespace"], "assistant_*")
        self.assertEqual(payload["isolated_from"], "cc_production")
        # Empty Hub → empty catalog (no stub KB rows).
        self.assertEqual(payload["items"], [])
        self.assertTrue(
            all(item["slug"].startswith("assistant_") for item in payload["items"])
        )

        created = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps({"name": "Legal docs", "slug": "legal"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["slug"], "assistant_legal")
        self.assertTrue(
            AssistantKnowledgeBase.objects.filter(slug="assistant_legal").exists()
        )
        self.assertFalse(
            CCProductionChunk.objects.filter(
                title__icontains="Legal docs"
            ).exists()
        )

        rejected = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps({"name": "Bad", "slug": "cc_production"}),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)

        kb_id = body["id"]
        upload = client.post(
            f"/api/admin/assistant/kb/{kb_id}/upload/",
            data={
                "file": SimpleUploadedFile(
                    "policy.txt",
                    b"Assistant policy text for RAG index.\n" * 20,
                    content_type="text/plain",
                )
            },
        )
        self.assertEqual(upload.status_code, 201, upload.content)
        uploaded = upload.json()
        self.assertEqual(uploaded["knowledge_base"]["status"], "ready")
        self.assertGreaterEqual(uploaded["document"]["chunk_count"], 1)
        self.assertTrue(
            AssistantProductionChunk.objects.filter(
                kb_slug="assistant_legal"
            ).exists()
        )
        self.assertFalse(
            CCProductionChunk.objects.filter(
                title="policy.txt"
            ).exists()
        )

        detail = client.get(f"/api/admin/assistant/kb/{kb_id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.json()["documents"]), 1)
        self.assertEqual(detail.json()["documents"][0]["index_percent"], 100)

    def test_upload_without_reindex_exposes_live_percent(self):
        from hub.kb_admin import document_index_percent
        from hub.models import AssistantKnowledgeBaseDocument

        self.assertEqual(document_index_percent("indexed", ""), 100)
        self.assertEqual(document_index_percent("uploaded", "Индексация 42%"), 42)
        self.assertEqual(document_index_percent("uploaded", ""), 0)

        client = Client()
        client.force_login(
            self.user_for_role("ai_assistant_module_administrator")
        )
        created = client.post(
            "/api/admin/assistant/kb/",
            data=json.dumps({"name": "Live percent", "slug": "live_percent"}),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        kb_id = created.json()["id"]
        upload = client.post(
            f"/api/admin/assistant/kb/{kb_id}/upload/",
            data={
                "file": SimpleUploadedFile(
                    "big.txt",
                    b"Live percent marker SUFLER-BIG-001.\n" * 40,
                    content_type="text/plain",
                ),
                "reindex": "0",
            },
        )
        self.assertEqual(upload.status_code, 201, upload.content)
        self.assertNotEqual(upload.json()["knowledge_base"]["status"], "ready")
        self.assertEqual(upload.json()["document"]["index_percent"], 0)
        document = AssistantKnowledgeBaseDocument.objects.get(
            pk=upload.json()["document"]["id"]
        )
        document.status_message = "Индексация 37%"
        document.save(update_fields=("status_message",))
        detail = client.get(f"/api/admin/assistant/kb/{kb_id}/")
        self.assertEqual(detail.json()["documents"][0]["index_percent"], 37)
        self.assertEqual(detail.json()["index_percent"], 37)

    def test_prompts_crud_and_capabilities_toggle(self):
        client = Client()
        client.force_login(
            self.user_for_role("llm_knowledge_base_administrator")
        )

        prompts = client.get("/api/admin/assistant/prompts/")
        self.assertEqual(prompts.status_code, 200)
        self.assertGreaterEqual(len(prompts.json()["items"]), 1)

        created = client.post(
            "/api/admin/assistant/prompts/",
            data=json.dumps(
                {
                    "name": "Task · тест",
                    "body": "Ответь кратко. KB={{kb}}",
                    "prompt_type": "task",
                    "kb_slug": "assistant_hr",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        prompt_id = created.json()["id"]

        updated = client.put(
            f"/api/admin/assistant/prompts/{prompt_id}/",
            data=json.dumps({"status": "published", "body": "Обновлено {{user}}"}),
            content_type="application/json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["status"], "published")
        self.assertGreaterEqual(updated.json()["version"], 2)

        caps = client.get("/api/admin/assistant/capabilities/")
        self.assertEqual(caps.status_code, 200)
        codes = {item["code"] for item in caps.json()["items"]}
        self.assertIn("rag_kb", codes)
        self.assertIn("rpa", codes)

        toggled = client.patch(
            "/api/admin/assistant/capabilities/rpa/",
            data=json.dumps({"enabled": True}),
            content_type="application/json",
        )
        self.assertEqual(toggled.status_code, 200)
        self.assertTrue(toggled.json()["enabled"])

        deleted = client.delete(f"/api/admin/assistant/prompts/{prompt_id}/")
        self.assertEqual(deleted.status_code, 200)

    def test_operator_forbidden(self):
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.get("/api/admin/assistant/prompts/")
        self.assertIn(response.status_code, (401, 403))
