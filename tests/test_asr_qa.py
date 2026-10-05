import json
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
from django.contrib.auth.models import Group  # noqa: E402
from django.test import Client, TestCase, override_settings  # noqa: E402

from auth.roles import ROLES_BY_CODE  # noqa: E402
from reports.asr_qa import seed_demo_sessions  # noqa: E402
from reports.models import AsrTranscriptUtterance  # noqa: E402


class AsrQaApiTest(TestCase):
    def user_for_role(self, role_code):
        role = ROLES_BY_CODE[role_code]
        user = get_user_model().objects.create_user(
            username=f"asr-qa-{role_code}",
            password="test-password",
        )
        group, _ = Group.objects.get_or_create(name=role.mock_ad_group)
        user.groups.add(group)
        return user

    def setUp(self):
        seed_demo_sessions(force=True)

    def test_analyst_lists_all_sessions_without_forced_low_confidence(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))

        response = client.get("/api/reports/asr/sessions/")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stats"]["total"], 3)
        self.assertFalse(payload["filters"]["low_confidence_only"])
        self.assertEqual(len(payload["items"]), 3)

        row = payload["items"][0]
        for key in (
            "started_at",
            "channel",
            "operator_name",
            "session_id",
            "duration_sec",
            "avg_confidence",
            "recognition_status",
        ):
            self.assertIn(key, row)

    def test_optional_low_confidence_filter_and_detail_card(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))

        filtered = client.get(
            "/api/reports/asr/sessions/",
            {"low_confidence_only": "true"},
        )
        self.assertEqual(filtered.status_code, 200)
        items = filtered.json()["items"]
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(
            all(item["min_confidence"] < 0.90 for item in items)
        )

        session_id = next(
            item["id"]
            for item in client.get("/api/reports/asr/sessions/").json()["items"]
            if item["session_id"] == "CALL-QA-002"
        )
        detail = client.get(f"/api/reports/asr/sessions/{session_id}/")
        self.assertEqual(detail.status_code, 200)
        body = detail.json()
        self.assertEqual(body["session_id"], "CALL-QA-002")
        self.assertTrue(body["audio_url"])
        self.assertGreaterEqual(len(body["utterances"]), 2)
        low = [u for u in body["utterances"] if u["low_confidence"]]
        self.assertGreaterEqual(len(low), 1)

        audio = client.get(f"/api/reports/asr/sessions/{session_id}/audio/")
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio["Content-Type"], "audio/wav")
        self.assertGreater(len(audio.content), 44)

    def test_mark_training_candidate_persisted(self):
        client = Client()
        client.force_login(self.user_for_role("contact_center_analyst"))

        session_id = next(
            item["id"]
            for item in client.get("/api/reports/asr/sessions/").json()["items"]
            if item["session_id"] == "CALL-QA-002"
        )
        utterance = AsrTranscriptUtterance.objects.get(
            session_id=session_id,
            is_unrecognized=True,
        )
        response = client.post(
            f"/api/reports/asr/sessions/{session_id}/utterances/{utterance.pk}/",
            data=json.dumps({"training_candidate": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["utterance"]["training_candidate"])
        self.assertTrue(payload["session"]["has_training_candidate"])

        utterance.refresh_from_db()
        self.assertTrue(utterance.training_candidate)
        self.assertEqual(utterance.annotated_by, "asr-qa-contact_center_analyst")

    @override_settings(DEBUG=False)
    def test_operator_forbidden(self):
        # DEBUG opens ASR QA for local SPA; assert RBAC when DEBUG is off.
        client = Client()
        client.force_login(
            self.user_for_role("contact_center_telephony_operator")
        )
        response = client.get("/api/reports/asr/sessions/")
        self.assertEqual(response.status_code, 403)
