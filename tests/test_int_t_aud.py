"""INT-T-AUD sample delivery to KUMA-compatible collector (VI.3).

P2-05 audit schema (schema_version=1.0) must remain unchanged.
"""

from __future__ import annotations

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

from django.test import SimpleTestCase, override_settings  # noqa: E402

from audit.events import (  # noqa: E402
    LOGIN_SUCCESS,
    SIEM_DELIVERY_FAILURE,
)
from audit.samples import (  # noqa: E402
    INT_T_AUD_SAMPLE_SPECS,
    emit_int_t_aud_samples,
)
from audit.service import (  # noqa: E402
    _configured_sink_names,
    configured_sinks,
    emit,
    resolve_kuma_collector_url,
)
from audit.schema import AuditSubject  # noqa: E402
from audit.events import CATEGORY_AUTHENTICATION, RESULT_SUCCESS  # noqa: E402
from audit.sinks.file import FileAuditSink  # noqa: E402
from audit.sinks.http import HttpAuditSink  # noqa: E402


class _KumaCollectorHandler(BaseHTTPRequestHandler):
    events: list[dict] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self.events.append(json.loads(self.rfile.read(length)))
        self.send_response(202)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"accepted":1}')

    def log_message(self, format, *args):
        del format, args


class IntTAudSamplesTest(SimpleTestCase):
    def setUp(self):
        _KumaCollectorHandler.events = []

    def test_p2_05_schema_version_unchanged_on_samples(self):
        events = emit_int_t_aud_samples(sinks=())
        self.assertEqual(len(events), len(INT_T_AUD_SAMPLE_SPECS))
        for event in events:
            self.assertEqual(event.schema_version, "1.0")
            payload = event.to_dict()
            self.assertEqual(payload["schema_version"], "1.0")
            self.assertIn("EventID", payload)
            self.assertIn("Timestamp", payload)
            self.assertIn("DeviceVendor", payload)
            self.assertIn("subject", payload)
            self.assertTrue(payload["subject"]["user_login"])

    def test_int_t_aud_samples_reach_kuma_collector(self):
        """INT-T-AUD-01/02: sample events delivered to collector URL."""
        server = ThreadingHTTPServer(("127.0.0.1", 0), _KumaCollectorHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        collector = f"http://127.0.0.1:{server.server_port}/v1/events"
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "audit.jsonl"
                with override_settings(
                    AUDIT_ENABLED=True,
                    AUDIT_SINKS=("file", "kuma"),
                    AUDIT_FILE_PATH=path,
                    AUDIT_KUMA_COLLECTOR_URL=collector,
                    AUDIT_HTTP_COLLECTOR_URL="",
                ):
                    self.assertEqual(resolve_kuma_collector_url(), collector)
                    sinks = configured_sinks()
                    self.assertTrue(
                        any(isinstance(s, FileAuditSink) for s in sinks)
                    )
                    self.assertTrue(
                        any(isinstance(s, HttpAuditSink) for s in sinks)
                    )
                    emitted = emit_int_t_aud_samples(sinks=sinks)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        self.assertEqual(len(_KumaCollectorHandler.events), len(emitted))
        received_types = {
            item["event_type"] for item in _KumaCollectorHandler.events
        }
        expected_types = {spec["event_type"] for spec in INT_T_AUD_SAMPLE_SPECS}
        self.assertEqual(received_types, expected_types)
        for item in _KumaCollectorHandler.events:
            self.assertEqual(item["schema_version"], "1.0")
            self.assertEqual(item["DeviceProduct"], "AI_Hub")
            self.assertIn("int_t_aud_id", item["details"])

    def test_kuma_alias_auto_enables_file_fallback(self):
        with override_settings(AUDIT_SINKS=("kuma",)):
            names = _configured_sink_names()
        self.assertEqual(names[0], "file")
        self.assertIn("http", names)

    def test_int_t_aud_03_fallback_when_collector_down(self):
        """INT-T-AUD-03: KUMA down → local JSONL + siem_delivery_failure."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            emit(
                category=CATEGORY_AUTHENTICATION,
                event_type=LOGIN_SUCCESS,
                result=RESULT_SUCCESS,
                subject=AuditSubject(user_login="int_t_aud.fallback"),
                module="auth",
                description="INT-T-AUD-03 fallback probe",
                details={"int_t_aud_id": "INT-T-AUD-03.fallback"},
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
        self.assertEqual(events[0]["schema_version"], "1.0")
        self.assertEqual(events[1]["event_type"], SIEM_DELIVERY_FAILURE)
        self.assertEqual(events[1]["result"], "failure")
        self.assertEqual(
            events[1]["details"]["failed_event_id"],
            events[0]["EventID"],
        )


if __name__ == "__main__":
    unittest.main()
