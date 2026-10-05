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
from django.test import Client, TestCase  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402


class AssReportsApiTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"ass-rpt-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_catalog_lists_fr_rpt_ass_ids(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_analyst"))

        response = client.get("/api/v1/assistant/reports/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["section"], "III.10.2")
        self.assertEqual(payload["permission"], "assistant.reports.view")
        ids = [item["id"] for item in payload["items"]]
        self.assertEqual(
            ids,
            [
                "FR-RPT-ASS-01",
                "FR-RPT-ASS-02",
                "FR-RPT-ASS-03",
                "FR-RPT-ASS-04",
                "FR-RPT-ASS-05",
                "FR-RPT-ASS-06",
                "FR-RPT-ASS-07",
                "FR-RPT-ASS-08",
            ],
        )

    def test_analyst_gets_analytics_usage_feedback_tools(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_analyst"))

        response = client.get(
            "/api/v1/assistant/reports/analytics/",
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-07",
                "department": "hr",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["stub"])
        self.assertIn("summary", payload)
        self.assertGreater(len(payload["rows"]), 0)
        self.assertTrue(
            all(row["department"] == "hr" for row in payload["rows"])
        )
        self.assertIn("FR-RPT-ASS-01", payload["sections"])
        self.assertIn("FR-RPT-ASS-02", payload["sections"])
        self.assertEqual(
            payload["sections"]["FR-RPT-ASS-02"]["feedback"]["fr_id"],
            "FR-RPT-ASS-02",
        )
        self.assertGreater(len(payload["tool_usage"]), 0)
        self.assertEqual(payload["filters"]["department"], "hr")

    def test_single_fr_report_detail(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_analyst"))

        response = client.get(
            "/api/v1/assistant/reports/FR-RPT-ASS-01/",
            {"date_from": "2026-07-01", "date_to": "2026-07-03"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["report_id"], "FR-RPT-ASS-01")
        self.assertEqual(set(payload["sections"].keys()), {"FR-RPT-ASS-01"})
        self.assertIn("relevance_by_type", payload["sections"]["FR-RPT-ASS-01"])

    def test_csv_and_xlsx_export_downloadable(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_analyst"))
        params = {
            "date_from": "2026-07-01",
            "date_to": "2026-07-03",
        }

        csv_response = client.get(
            "/api/v1/assistant/reports/export/",
            {**params, "format": "csv"},
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn("attachment", csv_response["Content-Disposition"])
        self.assertEqual(csv_response["X-FR-Catalog"], "FR-RPT-ASS")
        self.assertIn(b"date,department,query_type", csv_response.content)
        self.assertIn(b"FR-RPT-ASS-", csv_response.content)
        self.assertGreater(len(csv_response.content), 40)

        xlsx_response = client.get(
            "/api/v1/assistant/reports/export/",
            {**params, "format": "xlsx"},
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
            self.assertIn("avg_relevance_percent", sheet)
            self.assertIn("tool_calls", sheet)

    def test_reports_module_alias(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_analyst"))
        response = client.get("/api/reports/ass/analytics/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["stub"])
        export = client.get("/api/reports/ass/export/", {"format": "csv"})
        self.assertEqual(export.status_code, 200)
        self.assertEqual(export["X-FR-Catalog"], "FR-RPT-ASS")

    def test_forbidden_without_reports_permission(self):
        client = Client()
        client.force_login(self.user_for_role("ai_assistant_user"))
        response = client.get("/api/v1/assistant/reports/analytics/")
        self.assertIn(response.status_code, (401, 403))
