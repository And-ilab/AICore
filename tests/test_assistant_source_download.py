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
from django.db import connection  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.assistant_admin import (  # noqa: E402
    create_assistant_kb,
    upload_assistant_document,
)
from hub.models import (  # noqa: E402
    AssistantKnowledgeBaseDocument,
    ContactCenterKnowledgeBase,
    KnowledgeBaseDocument,
)
from ingest.models import CCProductionChunk  # noqa: E402


@override_settings()
class AssistantSourceDownloadTest(TestCase):
    def setUp(self):
        connection.ensure_connection()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(
            ASSISTANT_KB_STORAGE_ROOT=Path(self._tmpdir.name),
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        try:
            self._tmpdir.cleanup()
        except PermissionError:
            pass

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"src-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_download_original_from_chat_source(self):
        create_assistant_kb(
            {
                "name": "HR demo",
                "slug": "assistant_hr_dl",
                "description": "test",
            },
            username="tester",
        )
        from hub.models import AssistantKnowledgeBase

        kb = AssistantKnowledgeBase.objects.get(slug="assistant_hr_dl")
        payload = b"Hello source document content"
        upload_assistant_document(
            kb.pk,
            filename="zaiavlenie_ob_okazanii_fp040225.txt",
            content_type="text/plain",
            data=payload,
            username="tester",
            reindex=False,
        )
        document = AssistantKnowledgeBaseDocument.objects.get(
            knowledge_base=kb
        )
        self.assertTrue(document.original_relpath)

        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.get(
            "/api/v1/assistant/sources/download",
            {
                "kb_slug": kb.slug,
                "article_id": document.article_id,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = b"".join(response.streaming_content)
        self.assertEqual(body, payload)
        disposition = response["Content-Disposition"]
        self.assertIn("zaiavlenie_ob_okazanii_fp040225.txt", disposition)
        connection.ensure_connection()

    def test_open_suz_article_from_chat_source(self):
        CCProductionChunk.objects.create(
            article_id=91001,
            version_id=1,
            chunk_index=0,
            title="Перевод по номеру телефона",
            content="Как перевести деньги по номеру телефона внутри Беларуси.",
            permalink="https://suz.local/articles/91001",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:phone-transfer",
            embedding_model="stub",
            embedding=[0.0] * 1024,
            is_active=True,
        )
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.get(
            "/api/v1/assistant/sources/download",
            {"kb_slug": "suz-bitrix", "article_id": 91001},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("text/plain", response["Content-Type"])
        self.assertTrue(
            response["Content-Disposition"].lower().startswith("attachment")
            or "filename=" in response["Content-Disposition"]
            or "filename" in response.get("X-Source-Filename", "")
        )
        self.assertIn(".txt", response.get("X-Source-Filename", ""))
        self.assertIn("Перевод по номеру телефона".encode("utf-8"), response.content)
        self.assertIn("по номеру телефона".encode("utf-8"), response.content)
        self.assertIn(b"\n", response.content)

    def test_open_cc_uploaded_document_without_matching_slug(self):
        kb = ContactCenterKnowledgeBase.objects.create(
            name="КЦ продукты",
            slug="cc_products",
        )
        KnowledgeBaseDocument.objects.create(
            knowledge_base=kb,
            filename="perevod_po_telefonu.txt",
            content_type="text/plain",
            size_bytes=40,
            article_id=2_000_000_101,
            extracted_text="Перевод по номеру доступен в приложении.",
            status=KnowledgeBaseDocument.STATUS_INDEXED,
        )
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.get(
            "/api/v1/assistant/sources/download",
            {"kb_slug": "assistant_bank", "article_id": 2_000_000_101},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("в приложении".encode("utf-8"), response.content)
