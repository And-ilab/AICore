"""INT-T SUZ: Model B webhook (mock+prod) and INT-09 reconciliation fallback."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import uuid
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from celery import current_app  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from ingest.bitrix_client import (  # noqa: E402
    get_mock_bitrix_client,
    reset_mock_bitrix_client,
)
from ingest.models import CCProductionChunk, SuzReconcileState  # noqa: E402
from ingest.pipeline import checksum_for_text, normalize_text  # noqa: E402
from ingest.tasks import reconcile_suz_changes  # noqa: E402


def _published_event(**overrides):
    body = " ".join(f"банковский термин {index}" for index in range(80))
    payload = {
        "event_id": str(uuid.uuid4()),
        "event_type": "article.version_published",
        "occurred_at": "2026-07-20T12:00:00+03:00",
        "article_id": 501,
        "iblock_id": 42,
        "section_id": 3,
        "version_id": 2001,
        "version_number": 1,
        "is_current": True,
        "status": "published",
        "title": "Комиссия за перевод",
        "preview": "Кратко",
        "body_html": f"<p>{body}</p>",
        "body_plain": body,
        "permalink": "https://suz.local/articles/501",
        "locale": "ru",
        "visibility_scope": ["kc_operator"],
        "checksum": checksum_for_text(normalize_text(body)),
        "changed_fields": ["DETAIL_TEXT"],
    }
    payload.update(overrides)
    return payload


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    SUZ_INGEST_MODE="mock",
    SUZ_WEBHOOK_HMAC_SECRET="",
    SUZ_RECONCILE_ENABLED=True,
    BITRIX_REST_BASE_URL="",
)
class SuzIngestMockModeTest(TestCase):
    """INT-T on mock config: unsigned webhook + mock /changes polling."""

    def setUp(self):
        reset_mock_bitrix_client()
        SuzReconcileState.objects.all().delete()

    def test_reconcile_task_registered(self):
        self.assertIn(reconcile_suz_changes.name, current_app.tasks)

    def test_mock_webhook_accepts_without_hmac(self):
        payload = _published_event()
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        response = Client().post(
            "/api/v1/knowledge/events",
            data=body,
            content_type="application/json",
            HTTP_X_SUFLER_EVENT_ID=payload["event_id"],
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["ingest_mode"], "mock")
        self.assertTrue(
            CCProductionChunk.objects.filter(article_id=501, is_active=True).exists()
        )

    def test_int_09_reconcile_polls_mock_changes(self):
        event = _published_event(article_id=777, version_id=3001)
        mock = get_mock_bitrix_client()
        mock.seed(
            "1970-01-01T00:00:00+00:00",
            [event],
            cursor="2026-07-20T12:00:00+03:00",
        )

        response = Client().post("/api/v1/knowledge/reconcile/run/")
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["accepted"], 1)
        self.assertIn("INT-09", payload["acceptance"])
        self.assertTrue(
            CCProductionChunk.objects.filter(article_id=777, is_active=True).exists()
        )

        # Second run skips already ingested event_id.
        mock.seed(
            "2026-07-20T12:00:00+03:00",
            [event],
            cursor="2026-07-20T12:00:00+03:00",
        )
        again = Client().post("/api/v1/knowledge/reconcile/run/")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["skipped"], 1)
        self.assertEqual(again.json()["accepted"], 0)

        status = Client().get("/api/v1/knowledge/reconcile/")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["model"], "B")
        self.assertTrue(status.json()["cursor"])


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    SUZ_INGEST_MODE="prod",
    SUZ_WEBHOOK_HMAC_SECRET="prod-shared-secret",
    SUZ_ALLOWED_IBLOCK_IDS=frozenset({42}),
    SUZ_RECONCILE_ENABLED=True,
    BITRIX_REST_BASE_URL="",  # still use mock transport without base URL
)
class SuzIngestProdConfigTest(TestCase):
    """INT-T with prod-like env: HMAC required, iblock allowlist, reconcile on."""

    def setUp(self):
        reset_mock_bitrix_client()
        SuzReconcileState.objects.all().delete()

    def _post(self, payload, *, secret=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        headers = {
            "HTTP_X_SUFLER_EVENT_ID": payload["event_id"],
        }
        if secret:
            headers["HTTP_X_SUFLER_SIGNATURE"] = hmac.new(
                secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
        return Client().post(
            "/api/v1/knowledge/events",
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_prod_rejects_missing_hmac_and_wrong_iblock(self):
        payload = _published_event()
        unauthorized = self._post(payload)
        self.assertEqual(unauthorized.status_code, 401)

        accepted = self._post(payload, secret="prod-shared-secret")
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(accepted.json()["ingest_mode"], "prod")

        foreign = _published_event(iblock_id=99, event_id=str(uuid.uuid4()))
        rejected = self._post(foreign, secret="prod-shared-secret")
        self.assertEqual(rejected.status_code, 400)
        self.assertIn("iblock_id", rejected.json()["fields"])

    def test_prod_misconfigured_without_secret(self):
        with self.settings(SUZ_WEBHOOK_HMAC_SECRET=""):
            response = self._post(_published_event())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "misconfigured")

    def test_prod_reconcile_disabled_without_flag(self):
        with self.settings(SUZ_RECONCILE_ENABLED=False):
            response = Client().post("/api/v1/knowledge/reconcile/run/")
        self.assertEqual(response.status_code, 403)

    def test_prod_reconcile_ingests_from_mock_outbox(self):
        event = _published_event(article_id=888, version_id=4001)
        get_mock_bitrix_client().seed(
            "1970-01-01T00:00:00+00:00",
            [event],
            cursor="2026-07-21T10:00:00+03:00",
        )
        response = Client().post("/api/v1/knowledge/reconcile/run/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["accepted"], 1)
        self.assertTrue(
            CCProductionChunk.objects.filter(article_id=888, is_active=True).exists()
        )
