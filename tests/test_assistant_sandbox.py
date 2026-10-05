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
from django.test import RequestFactory, TestCase, override_settings  # noqa: E402

from assistant.sandbox import SandboxError, prepare_snippet  # noqa: E402


@override_settings(AUDIT_ENABLED=False)
class SandboxSnippetTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().post("/api/v1/assistant/sandbox/")
        user_model = get_user_model()
        self.request.user = user_model.objects.create_user(
            username="sandbox-dev",
            password="x",
        )

    def test_select_text_is_returned_and_not_a_query_result(self):
        payload = prepare_snippet("sql", "SELECT 1;", request=self.request)
        self.assertEqual(payload["kind"], "sql")
        self.assertEqual(payload["text"], "SELECT 1;")
        self.assertNotIn("rows", payload)

    def test_write_sql_is_rejected(self):
        with self.assertRaises(SandboxError):
            prepare_snippet("sql", "DELETE FROM cards", request=self.request)

    def test_second_statement_is_rejected(self):
        with self.assertRaises(SandboxError):
            prepare_snippet("sql", "SELECT 1; SELECT 2", request=self.request)

    def test_allowed_vitrine_is_accepted(self):
        payload = prepare_snippet(
            "sql",
            "SELECT id FROM cards",
            request=self.request,
        )
        self.assertEqual(payload["text"], "SELECT id FROM cards")

    def test_unknown_vitrine_is_rejected(self):
        with self.assertRaises(SandboxError):
            prepare_snippet("sql", "SELECT id FROM secret_table", request=self.request)

    def test_code_fragment_is_returned(self):
        payload = prepare_snippet("code", "print(1)", request=self.request)
        self.assertEqual(payload["text"], "print(1)")
        self.assertEqual(payload["label"], "Код")
