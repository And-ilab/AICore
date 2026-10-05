import hashlib
import hmac
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from celery import current_app  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from ingest.models import (  # noqa: E402
    CCProductionChunk,
    KnowledgeIngestEvent,
)
from ingest.pipeline import checksum_for_text, normalize_text  # noqa: E402
from ingest.tasks import reindex_kb  # noqa: E402
from qu.tasks import qu_retrain  # noqa: E402


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SuzIngestWebhookTest(TestCase):
    url = "/api/v1/knowledge/events"

    def test_celery_tasks_are_registered(self):
        self.assertIn(reindex_kb.name, current_app.tasks)
        self.assertIn(qu_retrain.name, current_app.tasks)

    @staticmethod
    def payload(**overrides):
        body = " ".join(f"банковский термин {index}" for index in range(220))
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "article.version_published",
            "occurred_at": "2026-07-20T12:00:00+03:00",
            "article_id": 101,
            "iblock_id": 7,
            "section_id": 3,
            "version_id": 1001,
            "version_number": 1,
            "is_current": True,
            "status": "published",
            "title": "Банковская статья",
            "preview": "Краткое описание",
            "body_html": f"<p>{body}</p>",
            "body_plain": body,
            "permalink": "https://suz.local/articles/101",
            "locale": "ru",
            "visibility_scope": ["kc_operator"],
            "checksum": checksum_for_text(normalize_text(body)),
            "changed_fields": ["DETAIL_TEXT"],
        }
        payload.update(overrides)
        return payload

    def post(self, payload, *, secret=""):
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {"HTTP_X_SUFLER_EVENT_ID": payload["event_id"]}
        if secret:
            headers["HTTP_X_SUFLER_SIGNATURE"] = hmac.new(
                secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).hexdigest()
        return Client().post(
            self.url,
            data=body,
            content_type="application/json",
            **headers,
        )

    def test_publish_upserts_pgvector_chunks_idempotently_by_article(self):
        payload = self.payload()
        response = self.post(payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["outcome"], "queued")
        first_count = CCProductionChunk.objects.filter(
            article_id=payload["article_id"]
        ).count()
        self.assertGreater(first_count, 0)

        duplicate = self.post(payload)
        self.assertEqual(duplicate.status_code, 202)
        self.assertEqual(duplicate.json()["status"], "accepted")
        self.assertEqual(
            CCProductionChunk.objects.filter(
                article_id=payload["article_id"]
            ).count(),
            first_count,
        )

        next_event = self.payload(
            event_id=str(uuid.uuid4()),
            version_id=1002,
            version_number=2,
        )
        unchanged = self.post(next_event)
        self.assertEqual(unchanged.status_code, 202)
        self.assertEqual(unchanged.json()["outcome"], "queued")
        self.assertEqual(
            set(
                CCProductionChunk.objects.filter(
                    article_id=payload["article_id"]
                ).values_list("version_id", flat=True)
            ),
            {1002},
        )
        self.assertEqual(KnowledgeIngestEvent.objects.count(), 2)

    def test_foreign_alphabet_payload_is_quarantined_before_indexing(self):
        body = "Порядок оформления карты 拆康济沙壅轰"
        payload = self.payload(
            body_plain=body,
            body_html=f"<p>{body}</p>",
            checksum=checksum_for_text(normalize_text(body)),
        )
        response = self.post(payload)
        self.assertEqual(response.status_code, 202)
        event = KnowledgeIngestEvent.objects.get(event_id=payload["event_id"])
        self.assertEqual(event.outcome, "language_quarantined")
        self.assertFalse(
            CCProductionChunk.objects.filter(
                article_id=payload["article_id"],
                is_active=True,
            ).exists()
        )

    def test_fake_article_runs_reindex_before_qu_retrain(self):
        payload = self.payload()
        original_run = qu_retrain.run
        observed = []

        def assert_index_committed(*args, **kwargs):
            observed.append(
                CCProductionChunk.objects.filter(
                    article_id=payload["article_id"],
                    is_active=True,
                ).exists()
            )
            return original_run(*args, **kwargs)

        with patch.object(qu_retrain, "run", side_effect=assert_index_committed):
            response = self.post(payload)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(observed, [True])

    def test_int_02_to_04_apply_expected_index_actions(self):
        published = self.payload()
        self.assertEqual(self.post(published).status_code, 202)

        draft = self.payload(
            event_id=str(uuid.uuid4()),
            event_type="article.updated",
            status="draft",
            is_current=False,
        )
        self.assertEqual(self.post(draft).json()["outcome"], "queued")
        self.assertTrue(CCProductionChunk.objects.filter(is_active=True).exists())

        archived = self.payload(
            event_id=str(uuid.uuid4()),
            event_type="article.unpublished",
            status="archived",
        )
        self.assertEqual(self.post(archived).json()["outcome"], "queued")
        self.assertFalse(
            CCProductionChunk.objects.filter(
                article_id=published["article_id"],
                is_active=True,
            ).exists()
        )

        deleted = {
            "event_id": str(uuid.uuid4()),
            "event_type": "article.deleted",
            "occurred_at": "2026-07-20T12:03:00+03:00",
            "article_id": 101,
            "iblock_id": 7,
        }
        self.assertEqual(self.post(deleted).json()["outcome"], "queued")
        self.assertFalse(
            CCProductionChunk.objects.filter(article_id=101).exists()
        )
    def test_hmac_and_checksum_are_validated(self):
        payload = self.payload()
        with self.settings(SUZ_WEBHOOK_HMAC_SECRET="shared-secret"):
            unauthorized = self.post(payload)
            accepted = self.post(payload, secret="shared-secret")
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(accepted.status_code, 202)

        invalid = self.payload(
            event_id=str(uuid.uuid4()),
            checksum=f"sha256:{'0' * 64}",
        )
        response = self.post(invalid)
        self.assertEqual(response.status_code, 400)
        self.assertIn("checksum", response.json()["fields"])
