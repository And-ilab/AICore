import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth.models import AnonymousUser  # noqa: E402
from django.contrib.auth.signals import user_login_failed  # noqa: E402
from django.http import JsonResponse  # noqa: E402
from django.test import RequestFactory, override_settings  # noqa: E402

from audit.events import (  # noqa: E402
    ACCESS_DENIED,
    AUDIT_CATEGORIES,
    CATEGORY_AUTHENTICATION,
    LOGIN_SUCCESS,
    RESULT_SUCCESS,
)
from audit.middleware import AuditMiddleware  # noqa: E402
from audit.schema import AuditSource, AuditSubject, build_event  # noqa: E402
from audit.service import emit  # noqa: E402
from audit.sinks.file import FileAuditSink  # noqa: E402
from audit.sinks.http import HttpAuditSink  # noqa: E402
from audit.sinks.memory import MemoryAuditSink  # noqa: E402


class _CollectorHandler(BaseHTTPRequestHandler):
    events = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.events.append(json.loads(self.rfile.read(length)))
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted":1}')

    def log_message(self, format, *args):
        del format, args


class AuditFoundationTest(unittest.TestCase):
    def setUp(self):
        _CollectorHandler.events = []

    def test_vi3_categories_are_valid_in_event_schema(self):
        for category in AUDIT_CATEGORIES:
            with self.subTest(category=category):
                event = build_event(
                    category=category,
                    event_type=f"hub.{category}.test",
                    result=RESULT_SUCCESS,
                    subject=AuditSubject(user_login="tester"),
                    source=AuditSource(service="test", module="audit"),
                    description="Schema test",
                    device_vendor="Belarusbank",
                    device_product="AI_Hub",
                    device_version="test",
                )
                self.assertEqual(event.category, category)
                self.assertTrue(event.EventID)
                self.assertTrue(event.Timestamp.endswith("Z"))

    @override_settings(AUDIT_ENABLED=True)
    def test_mock_sink_receives_structured_json(self):
        sink = MemoryAuditSink()

        event = emit(
            category=CATEGORY_AUTHENTICATION,
            event_type=LOGIN_SUCCESS,
            result=RESULT_SUCCESS,
            subject=AuditSubject(user_login="dev-role-01"),
            module="auth",
            description="Test login",
            sinks=(sink,),
        )

        self.assertEqual(len(sink.events), 1)
        self.assertEqual(sink.events[0]["EventID"], event.EventID)
        self.assertEqual(
            sink.events[0]["subject"]["user_login"],
            "dev-role-01",
        )

    def test_mock_http_collector_receives_json(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _CollectorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            event = build_event(
                category=CATEGORY_AUTHENTICATION,
                event_type=LOGIN_SUCCESS,
                result=RESULT_SUCCESS,
                subject=AuditSubject(user_login="http-user"),
                source=AuditSource(service="test", module="auth"),
                description="HTTP sink test",
                device_vendor="Belarusbank",
                device_product="AI_Hub",
                device_version="test",
            )
            HttpAuditSink(
                f"http://127.0.0.1:{server.server_port}/v1/events"
            ).write(event)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(len(_CollectorHandler.events), 1)
        self.assertEqual(
            _CollectorHandler.events[0]["EventID"],
            event.EventID,
        )

    def test_middleware_emits_denied_event_to_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            with override_settings(
                AUDIT_ENABLED=True,
                AUDIT_SINKS=("file",),
                AUDIT_FILE_PATH=path,
            ):
                middleware = AuditMiddleware(
                    lambda request: JsonResponse(
                        {"error": "permission_denied"},
                        status=403,
                    )
                )
                request = RequestFactory().get("/api/admin/protected/")
                request.user = AnonymousUser()
                response = middleware(request)

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["event_type"], ACCESS_DENIED)
        self.assertEqual(payload["result"], "failure")
        self.assertEqual(payload["outcome"]["http_status"], 403)

    @override_settings(AUDIT_ENABLED=True)
    def test_http_failure_keeps_local_event_and_emits_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            emit(
                category=CATEGORY_AUTHENTICATION,
                event_type=LOGIN_SUCCESS,
                result=RESULT_SUCCESS,
                subject=AuditSubject(user_login="fallback-user"),
                module="auth",
                description="Fallback test",
                sinks=(
                    FileAuditSink(path),
                    HttpAuditSink(
                        "http://127.0.0.1:1/v1/events",
                        timeout_seconds=0.1,
                    ),
                ),
            )
            events = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_type"], LOGIN_SUCCESS)
        self.assertEqual(
            events[1]["event_type"],
            "hub.integrations.siem_delivery_failure",
        )

    def test_auth_signal_emits_without_password(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            with override_settings(
                AUDIT_ENABLED=True,
                AUDIT_SINKS=("file",),
                AUDIT_FILE_PATH=path,
            ):
                request = RequestFactory().post("/admin/login/")
                request.user = AnonymousUser()
                user_login_failed.send(
                    sender=self.__class__,
                    credentials={
                        "username": "failed-user",
                        "password": "must-not-be-logged",
                    },
                    request=request,
                )
            raw_event = path.read_text(encoding="utf-8")
            event = json.loads(raw_event)

        self.assertEqual(
            event["event_type"],
            "hub.authentication.login_failure",
        )
        self.assertEqual(event["subject"]["user_login"], "failed-user")
        self.assertNotIn("must-not-be-logged", raw_event)


if __name__ == "__main__":
    unittest.main()
