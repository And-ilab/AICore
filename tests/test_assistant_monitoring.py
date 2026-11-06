import json
import os
import sys
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import AnonymousUser, Group  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db.utils import OperationalError  # noqa: E402
from django.test import Client, RequestFactory, TestCase  # noqa: E402
from django.utils import timezone as dj_timezone  # noqa: E402

from assistant.chat import NO_KB_ANSWER, iter_chat_sse  # noqa: E402
from assistant.models import (  # noqa: E402
    AssistantReportSchedule,
    AssistantReportTemplate,
    AssistantRequestEvent,
)
from assistant.monitoring_errors import (  # noqa: E402
    AggregationError,
    AuthenticationRequiredError,
    EventNotFoundError,
    ExportError,
    ExportTooLargeError,
    InvalidPeriodError,
    InvalidQueryError,
    MetricWriteError,
    MetricsStoreUnavailable,
    MonitoringError,
    MonitoringPermissionError,
    PeriodTooLargeError,
    QueryTimeoutError,
    ScheduleUnavailableError,
    monitoring_error_response,
)
from assistant.monitoring_record import record_chat_event  # noqa: E402
from auth.roles import ROLES_BY_CODE  # noqa: E402
from hub.models import AssistantAnswerFeedback  # noqa: E402


SECRET = "SECRET_DIALOG_40817810099999999999"


class MonitoringErrorResponseTest(TestCase):
    def response_for(self, exc):
        request = RequestFactory().get("/api/v1/assistant/monitoring/summary/")
        request.audit_request_id = "req-mon-1"
        request.user = AnonymousUser()
        return monitoring_error_response(exc, request)

    def test_each_error_class_hides_internals(self):
        cases = [
            (InvalidQueryError(), 400, "invalid_query"),
            (InvalidPeriodError(), 400, "invalid_period"),
            (PeriodTooLargeError(), 422, "period_too_large"),
            (EventNotFoundError(), 404, "not_found"),
            (AuthenticationRequiredError(), 401, "authentication_required"),
            (MonitoringPermissionError(), 403, "permission_denied"),
            (AggregationError(), 500, "aggregation_error"),
            (ExportError(), 500, "export_error"),
            (ExportTooLargeError(), 422, "export_too_large"),
            (MetricsStoreUnavailable(), 503, "store_unavailable"),
            (QueryTimeoutError(), 504, "query_timeout"),
            (MetricWriteError(), 500, "metric_write_error"),
            (ScheduleUnavailableError(), 503, "schedule_unavailable"),
            (MonitoringError(), 500, "monitoring_error"),
        ]
        for exc, status, code in cases:
            with self.subTest(code=code):
                response = self.response_for(exc)
                self.assertEqual(response.status_code, status)
                payload = json.loads(response.content)
                self.assertEqual(payload["error"], code)
                self.assertTrue(payload["message"])
                self.assertEqual(payload["request_id"], "req-mon-1")
                body = response.content.decode()
                self.assertNotIn("Traceback", body)
                self.assertNotIn("SELECT", body)
                self.assertNotIn(SECRET, body)


class AssistantMonitoringApiTest(TestCase):
    def setUp(self):
        self.client = Client()

    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"mon-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def login(self, role_code):
        self.client.force_login(self.user_for_role(role_code))

    def event(self, **overrides):
        payload = {
            "request_id": overrides.pop("request_id", "evt-1"),
            "message_id": "m-1",
            "username": "employee",
            "department": "hr",
            "query_type": AssistantRequestEvent.QUERY_RAG,
            "topic": "Отпуск",
            "outcome": AssistantRequestEvent.OUTCOME_STREAMED,
            "total_ms": 1000,
            "top_relevance": 80,
            "doc_count": 1,
            "question_text": SECRET,
            "answer_text": "ответ из базы",
        }
        payload.update(overrides)
        row = AssistantRequestEvent.objects.create(**payload)
        created_at = overrides.get("created_at")
        if created_at is not None:
            AssistantRequestEvent.objects.filter(pk=row.pk).update(created_at=created_at)
            row.refresh_from_db()
        return row

    def test_summary_numbers_and_empty_database(self):
        self.login("ai_assistant_analyst")
        empty = self.client.get("/api/v1/assistant/monitoring/summary/")
        self.assertEqual(empty.status_code, 200)
        widgets = empty.json()["widgets"]
        self.assertEqual(widgets["usefulness"]["status"], "empty")
        self.assertIsNone(widgets["usefulness"]["value"])
        self.assertIsNone(widgets["incorrect_answers"]["value"])
        self.assertIsNone(widgets["hallucinations"]["value"])
        self.assertNotIn(SECRET, empty.content.decode())

        moment = datetime(2026, 7, 1, 9, 0, tzinfo=timezone.utc)
        self.event(
            request_id="e1",
            message_id="m1",
            total_ms=1000,
            top_relevance=80,
            created_at=moment,
        )
        AssistantAnswerFeedback.objects.create(
            username="employee",
            message_id="m1",
            choice=AssistantAnswerFeedback.CHOICE_USEFUL,
        )
        self.event(
            request_id="e2",
            message_id="m2",
            total_ms=3000,
            top_relevance=40,
            created_at=moment,
        )
        AssistantAnswerFeedback.objects.create(
            username="employee",
            message_id="m2",
            choice=AssistantAnswerFeedback.CHOICE_INCORRECT,
        )
        self.event(
            request_id="e3",
            message_id="m3",
            query_type=AssistantRequestEvent.QUERY_LLM_ERROR,
            outcome=AssistantRequestEvent.OUTCOME_LLM_ERROR,
            error_reason=AssistantRequestEvent.REASON_LLM_ERROR,
            total_ms=2500,
            top_relevance=None,
            doc_count=0,
            topic="без источника",
            created_at=moment,
        )
        self.event(
            request_id="e4",
            message_id="m4",
            username="other",
            department="it",
            query_type=AssistantRequestEvent.QUERY_NO_KB,
            outcome=AssistantRequestEvent.OUTCOME_NO_KB,
            error_reason=AssistantRequestEvent.REASON_NO_SOURCES,
            total_ms=500,
            top_relevance=None,
            doc_count=0,
            hallucination_marked=True,
            created_at=moment,
        )

        response = self.client.get(
            "/api/v1/assistant/monitoring/summary/",
            {"date_from": "2026-07-01", "date_to": "2026-07-01"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["widgets"]["usefulness"]["value"], 25.0)
        self.assertEqual(body["widgets"]["incorrect_answers"]["value"], 50.0)
        self.assertEqual(body["widgets"]["hallucinations"]["value"], 25.0)
        self.assertEqual(body["widgets"]["latency"]["avg_ms"], 1750.0)
        self.assertEqual(body["widgets"]["latency"]["max_ms"], 3000.0)
        self.assertEqual(body["widgets"]["latency"]["p95_ms"], 3000.0)
        self.assertEqual(body["widgets"]["latency"]["over_sla_pct"], 50.0)
        self.assertNotIn(SECRET, response.content.decode())

        narrowed = self.client.get(
            "/api/v1/assistant/monitoring/summary/",
            {
                "date_from": "2026-07-01",
                "date_to": "2026-07-01",
                "department": "hr",
            },
        )
        self.assertEqual(narrowed.json()["widgets"]["usefulness"]["value"], 33.3)

    def test_roles(self):
        url = "/api/v1/assistant/monitoring/summary/"
        self.assertEqual(self.client.get(url).status_code, 401)
        self.login("ai_assistant_user")
        self.assertEqual(self.client.get(url).status_code, 403)
        self.login("contact_center_telephony_operator")
        self.assertEqual(self.client.get(url).status_code, 403)
        for role in (
            "ai_assistant_analyst",
            "software_administrator",
            "ai_assistant_module_administrator",
            "llm_knowledge_base_administrator",
        ):
            client = Client()
            client.force_login(self.user_for_role(role))
            self.assertEqual(client.get(url).status_code, 200, role)

    def test_minsk_day_boundary_and_one_day_period(self):
        self.login("ai_assistant_analyst")
        # 21:30 UTC is 00:30 next calendar day in Minsk, including the EU DST date.
        self.event(
            request_id="boundary",
            created_at=datetime(2020, 3, 28, 21, 30, tzinfo=timezone.utc),
            total_ms=1500,
            top_relevance=70,
        )
        before = self.client.get(
            "/api/v1/assistant/monitoring/series/",
            {
                "date_from": "2020-03-28",
                "date_to": "2020-03-28",
                "grain": "day",
                "metric": "relevance",
            },
        )
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.json()["points"][0]["sessions"], 0)
        after = self.client.get(
            "/api/v1/assistant/monitoring/series/",
            {
                "date_from": "2020-03-29",
                "date_to": "2020-03-29",
                "grain": "hour",
                "metric": "latency",
            },
        )
        self.assertEqual(after.status_code, 200)
        points = {item["bucket"]: item["sessions"] for item in after.json()["points"]}
        self.assertEqual(points["2020-03-29T00:00"], 1)
        self.assertEqual(sum(points.values()), 1)

    def test_validation_pagination_and_stable_order(self):
        self.login("ai_assistant_analyst")
        stamp = datetime(2026, 7, 3, 8, 0, tzinfo=timezone.utc)
        first = self.event(request_id="sort-a", created_at=stamp, total_ms=100)
        second = self.event(request_id="sort-b", message_id="m-b", created_at=stamp, total_ms=100)
        self.assertLess(first.pk, second.pk)

        page = self.client.get(
            "/api/v1/assistant/monitoring/events/",
            {
                "date_from": "2026-07-03",
                "date_to": "2026-07-03",
                "order": "created_at",
                "page": 1,
                "page_size": 1,
            },
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.json()["items"][0]["id"], first.pk)
        self.assertNotIn("question_text", page.json()["items"][0])
        self.assertNotIn(SECRET, page.content.decode())
        next_page = self.client.get(
            "/api/v1/assistant/monitoring/events/",
            {
                "date_from": "2026-07-03",
                "date_to": "2026-07-03",
                "order": "created_at",
                "page": 2,
                "page_size": 1,
            },
        )
        self.assertEqual(next_page.json()["items"][0]["id"], second.pk)
        beyond = self.client.get(
            "/api/v1/assistant/monitoring/events/",
            {"date_from": "2026-07-03", "date_to": "2026-07-03", "page": 99},
        )
        self.assertEqual(beyond.status_code, 200)
        self.assertEqual(beyond.json()["items"], [])
        self.assertGreaterEqual(beyond.json()["total"], 2)

        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/events/",
                {"page_size": "0"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/events/",
                {"page": "-1"},
            ).status_code,
            400,
        )
        bad_order = self.client.get(
            "/api/v1/assistant/monitoring/events/",
            {"order": "name;drop"},
        )
        self.assertEqual(bad_order.status_code, 400)
        self.assertEqual(bad_order.json()["error"], "invalid_query")
        self.assertNotIn("drop", bad_order.content.decode().lower())
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/summary/",
                {"date_from": "2026-12-01", "date_to": "2026-12-02"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/summary/",
                {"date_from": "2026-07-02", "date_to": "2026-07-01"},
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/summary/",
                {"date_from": "2024-01-01", "date_to": "2026-07-01"},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/summary/",
                {"date_from": "07-01-2026"},
            ).status_code,
            400,
        )
        unknown = self.client.get(
            "/api/v1/assistant/monitoring/summary/",
            {"foo": "bar"},
        )
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(unknown.json()["error"], "invalid_query")
        self.assertEqual(
            self.client.get(
                "/api/v1/assistant/monitoring/events/",
                {"query_type": "not-a-type"},
            ).status_code,
            400,
        )

    def test_detail_deleted_and_hallucination_mark(self):
        self.login("ai_assistant_analyst")
        row = self.event(request_id="detail-1", message_id="md-1")
        missing = self.client.get("/api/v1/assistant/monitoring/events/999999/")
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json()["error"], "not_found")
        self.assertNotIn("SELECT", missing.content.decode())

        detail = self.client.get(f"/api/v1/assistant/monitoring/events/{row.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["question_text"], SECRET)
        listed = self.client.get(
            "/api/v1/assistant/monitoring/events/",
            {"kind": "all", "date_from": "2026-11-06", "date_to": "2026-11-06"},
        )
        self.assertNotIn(SECRET, listed.content.decode())

        marked = self.client.post(
            f"/api/v1/assistant/monitoring/events/{row.pk}/hallucination/",
            data=json.dumps({"marked": True}),
            content_type="application/json",
        )
        self.assertEqual(marked.status_code, 200)
        self.assertTrue(marked.json()["hallucination_marked"])
        row.delete()
        gone = self.client.get(f"/api/v1/assistant/monitoring/events/{row.pk}/")
        self.assertEqual(gone.status_code, 404)

    def test_store_failure_does_not_leak_and_widget_degrades(self):
        self.login("ai_assistant_analyst")
        self.event(request_id="widget-1", message_id="mw-1", total_ms=800, top_relevance=90)
        with patch(
            "assistant.monitoring_query.percentile_total_ms",
            side_effect=RuntimeError("SELECT secret_p95"),
        ):
            summary = self.client.get(
                "/api/v1/assistant/monitoring/summary/",
                {"date_from": "2026-11-01", "date_to": "2026-11-06"},
            )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["widgets"]["latency"]["status"], "error")
        self.assertNotEqual(body["widgets"]["usefulness"]["status"], "error")
        self.assertNotIn("secret_p95", summary.content.decode())
        self.assertNotIn("SELECT", summary.content.decode())

        with patch(
            "assistant.monitoring_query.AssistantRequestEvent.objects.filter",
            side_effect=OperationalError('relation "secret_table" does not exist'),
        ):
            broken = self.client.get("/api/v1/assistant/monitoring/events/")
        self.assertEqual(broken.status_code, 503)
        self.assertEqual(broken.json()["error"], "store_unavailable")
        self.assertNotIn("secret_table", broken.content.decode())

    def test_export_template_and_schedule(self):
        self.login("ai_assistant_analyst")
        self.event(
            request_id="export-1",
            created_at=datetime(2026, 7, 2, 9, 0, tzinfo=timezone.utc),
        )
        with self.assertLogs("assistant.monitoring", level="INFO") as captured:
            exported = self.client.get(
                "/api/v1/assistant/reports/export/",
                {"date_from": "2026-07-01", "date_to": "2026-07-03", "format": "csv"},
            )
        self.assertEqual(exported.status_code, 200)
        exported_body = b"".join(exported.streaming_content)
        self.assertIn(b"FR-RPT-ASS-", exported_body)
        self.assertNotIn(SECRET, "\n".join(captured.output))
        self.assertNotIn(SECRET, exported_body.decode())

        created = self.client.post(
            "/api/v1/assistant/monitoring/templates/",
            data=json.dumps(
                {
                    "name": "Сводка",
                    "metrics": ["requests_total", "avg_relevance"],
                    "format": "csv",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        rejected = self.client.post(
            "/api/v1/assistant/monitoring/templates/",
            data=json.dumps(
                {"name": "Плохой", "metrics": ["drop_table"], "format": "csv"}
            ),
            content_type="application/json",
        )
        self.assertEqual(rejected.status_code, 400)
        self.assertEqual(rejected.json()["error"], "invalid_query")

        schedule = self.client.post(
            "/api/v1/assistant/monitoring/schedules/",
            data=json.dumps(
                {
                    "cadence": "daily",
                    "report_id": "FR-RPT-ASS-01",
                    "enabled": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(schedule.status_code, 201)
        schedule_id = schedule.json()["id"]
        with patch(
            "assistant.monitoring_views.run_due_report_schedules.delay",
            side_effect=ConnectionError("redis://secret-broker"),
        ):
            queued = self.client.post(
                f"/api/v1/assistant/monitoring/schedules/{schedule_id}/run/",
            )
        self.assertEqual(queued.status_code, 503)
        self.assertEqual(queued.json()["error"], "schedule_unavailable")
        self.assertNotIn("secret-broker", queued.content.decode())
        stored = AssistantReportSchedule.objects.get(pk=schedule_id)
        self.assertEqual(stored.last_error, "broker_unavailable")

    def test_metric_write_does_not_break_chat_or_duplicate(self):
        messages = [{"role": "user", "content": SECRET}]
        with patch(
            "assistant.chat.retrieve_assistant_context",
            return_value=([], 0),
        ), patch(
            "assistant.monitoring_record.AssistantRequestEvent.objects.get_or_create",
            side_effect=RuntimeError("db down"),
        ), self.assertLogs("assistant.monitoring", level="WARNING") as captured:
            frames = "".join(
                iter_chat_sse(
                    messages,
                    kb_slugs=["assistant_demo"],
                    request_id="chat-1",
                    message_id="asst-1",
                    actor="employee",
                )
            )
        self.assertIn(NO_KB_ANSWER[:24], frames)
        self.assertNotIn(SECRET, "\n".join(captured.output))

        record_chat_event(
            request_id="same-request",
            message_id="asst-2",
            username="employee",
            question_text=SECRET,
            answer_text="первый",
            outcome="no_kb",
            total_ms=100,
            doc_count=0,
        )
        record_chat_event(
            request_id="same-request",
            message_id="asst-2",
            username="employee",
            question_text=SECRET,
            answer_text="второй",
            outcome="no_kb",
            total_ms=250,
            doc_count=0,
        )
        rows = AssistantRequestEvent.objects.filter(request_id="same-request")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().total_ms, 250)
        self.assertEqual(rows.get().answer_text, "второй")

    def test_purge_keeps_the_recent_year(self):
        old = self.event(request_id="old-event")
        fresh = self.event(request_id="fresh-event", message_id="fresh")
        AssistantRequestEvent.objects.filter(pk=old.pk).update(
            created_at=dj_timezone.now() - timedelta(days=400),
        )
        call_command("purge_assistant_monitoring_events", stdout=StringIO())
        self.assertFalse(AssistantRequestEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(AssistantRequestEvent.objects.filter(pk=fresh.pk).exists())

    def test_schedule_snapshot_has_no_dialog_text(self):
        self.event(
            request_id="snap-1",
            question_text=SECRET,
            answer_text=SECRET,
        )
        schedule = AssistantReportSchedule.objects.create(
            cadence=AssistantReportSchedule.CADENCE_DAILY,
            report_id="FR-RPT-ASS-02",
            enabled=True,
        )
        from assistant.tasks import run_due_report_schedules

        run_due_report_schedules(schedule.pk)
        schedule.refresh_from_db()
        self.assertEqual(schedule.last_status, AssistantReportSchedule.STATUS_OK)
        blob = json.dumps(schedule.last_summary, ensure_ascii=False)
        self.assertNotIn(SECRET, blob)
        self.assertIn("sessions", schedule.last_summary)

    def test_template_round_trip_whitelist(self):
        self.login("ai_assistant_analyst")
        created = self.client.post(
            "/api/v1/assistant/monitoring/templates/",
            data=json.dumps(
                {"name": "Месяц", "metrics": ["error_rate"], "format": "xlsx"}
            ),
            content_type="application/json",
        )
        template_id = created.json()["id"]
        self.assertTrue(AssistantReportTemplate.objects.filter(pk=template_id).exists())
        removed = self.client.delete(
            f"/api/v1/assistant/monitoring/templates/{template_id}/",
        )
        self.assertEqual(removed.status_code, 204)
        self.assertEqual(
            self.client.get(
                f"/api/v1/assistant/monitoring/templates/{template_id}/",
            ).status_code,
            404,
        )
