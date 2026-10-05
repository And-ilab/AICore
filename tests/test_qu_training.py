import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from online_chat.models import SuflerHintFeedback  # noqa: E402
from qu.admin_service import enqueue_from_feedback, hash_question  # noqa: E402
from qu.models import QuReferenceExample, QuReplenishmentPolicy  # noqa: E402
from reports.asr_qa import set_training_candidate  # noqa: E402
from reports.cc_chat_metrics import sufler_stats  # noqa: E402
from reports.models import AsrDialogueSession, AsrTranscriptUtterance  # noqa: E402


class QuTrainingAdminTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"qu-train-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def test_crud_review_and_policy(self):
        client = Client()
        client.force_login(self.user_for_role("llm_knowledge_base_administrator"))
        with patch("qu.admin_service.qu_retrain.delay"):
            created = client.post(
                "/api/admin/qu/examples/",
                data=json.dumps(
                    {
                        "question": "Как заменить ПИН?",
                        "intent_id": "PIN-REPLACE",
                        "article_id": 101,
                        "synonyms": "пин-код, код карты",
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(created.status_code, 201, created.content)
        body = created.json()
        self.assertEqual(body["status"], "active")
        self.assertTrue(body["is_active"])

        listing = client.get("/api/admin/qu/examples/?status=active")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.json()["items"]), 1)

        policy = client.put(
            "/api/admin/qu/policy/",
            data=json.dumps({"mode": "suggest"}),
            content_type="application/json",
        )
        self.assertEqual(policy.status_code, 200)
        self.assertEqual(policy.json()["mode"], "suggest")

        pending = QuReferenceExample.objects.create(
            question="Где получить справку?",
            question_hash=hash_question("Где получить справку?"),
            status=QuReferenceExample.STATUS_PENDING,
            is_active=False,
            source=QuReferenceExample.SOURCE_DIALOG,
            original_hint="Обратитесь позже",
        )
        with patch("qu.admin_service.qu_retrain.delay"):
            reviewed = client.post(
                f"/api/admin/qu/examples/{pending.pk}/review/",
                data=json.dumps(
                    {
                        "action": "approve",
                        "intent_id": "CERT-ISSUE",
                        "article_id": 202,
                        "admin_comment": "Сопоставить со справками",
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(reviewed.status_code, 200, reviewed.content)
        pending.refresh_from_db()
        self.assertEqual(pending.status, QuReferenceExample.STATUS_ACTIVE)
        self.assertTrue(pending.is_active)

    def test_feedback_enqueue_dedup_and_asr_candidate(self):
        QuReplenishmentPolicy.objects.create(
            mode=QuReplenishmentPolicy.MODE_AUTO_CONFIRM,
        )
        feedback = SuflerHintFeedback.objects.create(
            query="Как заменить ПИН?",
            hint_text="Обратитесь позже.",
            choice="not_used",
            operator_name="Иванова",
            source="telephony",
            relevance_percent=41,
        )
        first = enqueue_from_feedback(feedback)
        second = enqueue_from_feedback(feedback)
        self.assertIsNotNone(first)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, QuReferenceExample.STATUS_PENDING)
        self.assertFalse(first.is_active)
        self.assertEqual(first.channel, "telephony")

        now = timezone.now()
        session = AsrDialogueSession.objects.create(
            session_id="CALL-QA-TEST",
            channel=AsrDialogueSession.CHANNEL_TELEPHONY,
            operator_name="Иванов",
            started_at=now,
            ended_at=now + timedelta(seconds=20),
            duration_sec=20,
            avg_confidence=0.9,
            min_confidence=0.8,
            recognition_status=AsrDialogueSession.STATUS_RECOGNIZED,
            expires_at=now + timedelta(days=30),
        )
        utterance = AsrTranscriptUtterance.objects.create(
            session=session,
            turn_index=0,
            speaker=AsrTranscriptUtterance.SPEAKER_CLIENT,
            text="Хочу узнать лимит по карте",
            confidence=0.94,
            start_ms=1000,
            end_ms=4000,
        )
        result = set_training_candidate(
            session.pk,
            utterance.pk,
            training_candidate=True,
            username="analyst",
        )
        self.assertTrue(result["utterance"]["training_candidate"])
        queued = QuReferenceExample.objects.get(
            question_hash=hash_question("Хочу узнать лимит по карте")
        )
        self.assertEqual(queued.status, QuReferenceExample.STATUS_PENDING)
        self.assertEqual(queued.source, QuReferenceExample.SOURCE_ASR)

    def test_sufler_stats_splits_chat_and_telephony(self):
        today = timezone.now().date()
        SuflerHintFeedback.objects.create(
            query="q1", hint_text="h1", choice="used", source="chat"
        )
        SuflerHintFeedback.objects.create(
            query="q2", hint_text="h2", choice="not_used", source="telephony"
        )
        stats = sufler_stats(today, today)
        self.assertEqual(stats["total"], 2)
        channels = {row["channel"] for row in stats["by_source"]}
        self.assertEqual(channels, {"chat", "telephony"})
        unused = next(row for row in stats["by_choice"] if row["choice"] == "not_used")
        self.assertEqual(unused["label"], "Не воспользовался")
