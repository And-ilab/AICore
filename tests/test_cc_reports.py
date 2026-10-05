import os
import sys
import zipfile
from io import BytesIO
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402
from django.utils import timezone  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from online_chat.models import SuflerHintFeedback  # noqa: E402


class CcReportsApiTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"cc-rpt-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_analyst_gets_analytics_with_asr_charts(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))

        response = client.get(
            "/api/reports/cc/analytics/",
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-07",
                "channel": "telephony",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["stub"])
        self.assertIn("summary", payload)
        self.assertGreater(len(payload["rows"]), 0)
        self.assertEqual(payload["filters"]["channel"], "telephony")
        self.assertTrue(
            all(row["channel"] == "telephony" for row in payload["rows"])
        )

        chat = client.get(
            "/api/reports/cc/analytics/",
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-07",
                "channel": "online_chat",
            },
        )
        self.assertEqual(chat.status_code, 200)
        chat_body = chat.json()
        self.assertEqual(chat_body["filters"]["channel"], "online_chat")
        self.assertIn("Онлайн-чат", chat_body["source"])

    def test_csv_and_xlsx_export_downloadable(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))
        params = {
            "date_from": "2026-07-01",
            "date_to": "2026-07-03",
        }

        csv_response = client.get(
            "/api/reports/cc/export/",
            {**params, "format": "csv", "report": "chat-topics"},
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn("attachment", csv_response["Content-Disposition"])
        self.assertIn("Категория".encode("utf-8"), csv_response.content)
        self.assertGreater(len(csv_response.content), 40)

        xlsx_response = client.get(
            "/api/reports/cc/export/",
            {**params, "format": "xlsx", "report": "chat-topics"},
        )
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertIn(
            "spreadsheetml.sheet",
            xlsx_response["Content-Type"],
        )
        self.assertIn(".xlsx", xlsx_response["Content-Disposition"])
        with zipfile.ZipFile(BytesIO(xlsx_response.content)) as archive:
            names = archive.namelist()
            self.assertIn("xl/worksheets/sheet1.xml", names)
            sheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertIn("Категория", sheet)

        pdf_response = client.get(
            "/api/reports/cc/export/",
            {**params, "format": "pdf", "report": "chat-topics"},
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertIn("pdf", pdf_response["Content-Type"])
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    def _pdf_text(self, content: bytes) -> str:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    def test_categories_pdf_uses_analyst_full_name(self):
        client = Client()
        user = self.user_for_role("contact_center_analyst")
        user.first_name = "Иван"
        user.last_name = "Петров"
        user.save(update_fields=["first_name", "last_name"])
        client.force_login(user)

        response = client.get(
            "/api/reports/cc/export/",
            {
                "date_from": "2026-08-18",
                "date_to": "2026-08-24",
                "format": "pdf",
                "report": "chat-topics",
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertTrue(response.content.startswith(b"%PDF"))
        text = self._pdf_text(response.content)
        self.assertIn("ОТЧЁТ", text)
        self.assertIn("Статистика по категориям", text)
        self.assertIn("Дата формирования", text)
        self.assertIn("Сформировал", text)
        self.assertIn("Петров Иван", text)
        self.assertIn("18.08.2026", text)
        self.assertIn("24.08.2026", text)
        self.assertIn("Категория", text)
        self.assertIn("Онлайн-чат", text)
        self.assertIn("Стр.", text)

    def test_categories_pdf_fallback_author_without_name(self):
        client = Client()
        user = self.user_for_role("contact_center_analyst")
        user.first_name = ""
        user.last_name = ""
        user.save(update_fields=["first_name", "last_name"])
        client.force_login(user)

        response = client.get(
            "/api/reports/cc/export/",
            {
                "date_from": "2026-08-18",
                "date_to": "2026-08-24",
                "format": "pdf",
                "report": "chat-topics",
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        text = self._pdf_text(response.content)
        self.assertIn("Антонов В.А.", text)
        self.assertNotIn(user.username, text)

    def test_categories_pdf_replaces_mock_ad_name(self):
        client = Client()
        user = self.user_for_role("contact_center_analyst")
        user.first_name = "Dev"
        user.last_name = "Role 01"
        user.save(update_fields=["first_name", "last_name"])
        client.force_login(user)

        response = client.get(
            "/api/reports/cc/export/",
            {
                "date_from": "2026-08-18",
                "date_to": "2026-08-24",
                "format": "pdf",
                "report": "chat-topics",
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:500])
        text = self._pdf_text(response.content)
        self.assertIn("Антонов В.А.", text)
        self.assertNotIn("Role 01", text)
        self.assertNotIn("Dev", text)

    @override_settings(DEBUG=False)
    def test_forbidden_without_reports_permission(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_telephony_operator"))
        response = client.get("/api/reports/cc/analytics/")
        self.assertIn(response.status_code, (401, 403))

    def test_live_and_catalog_endpoints(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))

        live = client.get("/api/reports/cc/live/")
        self.assertEqual(live.status_code, 200)
        live_body = live.json()
        self.assertIn("kpis", live_body)
        self.assertIn("operators", live_body)

        catalog = client.get(
            "/api/reports/cc/catalog/",
            {"report": "chat-topics", "date_from": "2026-07-01", "date_to": "2026-07-07"},
        )
        self.assertEqual(catalog.status_code, 200)
        catalog_body = catalog.json()
        self.assertEqual(catalog_body["report"]["id"], "chat-topics")
        self.assertIn("catalog", catalog_body)
        catalog_ids = {item["id"] for item in catalog_body["catalog"]}
        self.assertIn("chat-topics", catalog_ids)
        self.assertIn("chat-time-usage", catalog_ids)
        self.assertNotIn("chat-sla", catalog_ids)
        self.assertNotIn("usefulness", catalog_ids)

        sufler = client.get(
            "/api/reports/cc/catalog/",
            {
                "report": "chat-period",
                "scope": "sufler",
                "date_from": "2026-07-01",
                "date_to": "2026-07-07",
            },
        )
        self.assertEqual(sufler.status_code, 200)
        sufler_body = sufler.json()
        self.assertEqual(sufler_body["report"]["id"], "usefulness")
        self.assertEqual(sufler_body["source"], "Суфлёр")
        self.assertEqual(sufler_body["filters"]["channel"], "")
        catalog_ids = {item["id"] for item in sufler_body["catalog"]}
        self.assertEqual(
            catalog_ids,
            {"usefulness", "relevance", "errors"},
        )
        self.assertNotIn("chat-sla", catalog_ids)
        self.assertNotIn("chat-period", catalog_ids)

        errors = client.get(
            "/api/reports/cc/catalog/",
            {
                "report": "errors",
                "scope": "sufler",
                "date_from": "2026-08-05",
                "date_to": "2026-08-20",
            },
        )
        self.assertEqual(errors.status_code, 200)
        errors_body = errors.json()
        self.assertEqual(errors_body["report"]["id"], "errors")
        self.assertGreater(len(errors_body["rows"]), 0)
        self.assertTrue(errors_body["stub"])

        builder = client.get("/api/reports/cc/builder/")
        self.assertEqual(builder.status_code, 200)
        self.assertIn("templates", builder.json())
        self.assertFalse(builder.json().get("stub", True))

        preview = client.post(
            "/api/reports/cc/builder/preview/",
            data='{"metrics":["dialogs_total","csat"],"name":"t"}',
            content_type="application/json",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn("rows", preview.json())

    def test_sufler_stats_include_telephony_without_channel_filter(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))
        SuflerHintFeedback.objects.create(
            query="Со скольки лет можно взять?",
            hint_text="С 14 лет при согласии законного представителя.",
            choice="not_used",
            operator_name="dev-role-01",
            source="telephony",
            relevance_percent=62,
        )
        day = timezone.now().date().isoformat()
        errors = client.get(
            "/api/reports/cc/catalog/",
            {
                "report": "errors",
                "scope": "sufler",
                "date_from": day,
                "date_to": day,
            },
        )
        self.assertEqual(errors.status_code, 200)
        body = errors.json()
        self.assertEqual(body["filters"]["channel"], "")
        self.assertFalse(body["stub"])
        self.assertGreaterEqual(body["summary"].get("cases", 0), 1)
        examples = " ".join(str(row.get("example") or "") for row in body["rows"])
        self.assertIn("Со скольки лет можно взять?", examples)

        chat_only = client.get(
            "/api/reports/cc/catalog/",
            {
                "report": "errors",
                "scope": "sufler",
                "channel": "online_chat",
                "date_from": day,
                "date_to": day,
            },
        )
        self.assertEqual(chat_only.status_code, 200)
        chat_body = chat_only.json()
        chat_examples = " ".join(
            str(row.get("example") or "") for row in chat_body["rows"]
        )
        self.assertNotIn("Со скольки лет можно взять?", chat_examples)

        relevance = client.get(
            "/api/reports/cc/catalog/",
            {
                "report": "relevance",
                "scope": "sufler",
                "group_by": "none",
                "date_from": day,
                "date_to": day,
            },
        )
        self.assertEqual(relevance.status_code, 200)
        rel_body = relevance.json()
        self.assertEqual(rel_body["report"]["default_view"], "pie")
        self.assertGreaterEqual(len(rel_body["chart"]), 1)
        self.assertTrue(
            any("Средняя" in str(item.get("label") or "") for item in rel_body["chart"])
        )

    def test_customer_report_templates_build(self):
        from reports.cc_catalog import VISIBLE_REPORT_TYPES

        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))
        report_ids = [item["id"] for item in VISIBLE_REPORT_TYPES]
        self.assertEqual(len(report_ids), 11)
        for report_id in report_ids:
            response = client.get(
                "/api/reports/cc/catalog/",
                {
                    "report": report_id,
                    "date_from": "2026-08-18",
                    "date_to": "2026-08-24",
                },
            )
            self.assertEqual(response.status_code, 200, response.content)
            body = response.json()
            self.assertEqual(body["report"]["id"], report_id)
            self.assertIn("columns", body)
            self.assertIn("rows", body)

