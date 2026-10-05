"""Acceptance: widget dialogs, close → post-chat feedback + transcript e-mail."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django

django.setup()

from django.core import mail
from django.test import Client, TestCase, override_settings

from online_chat.models import Dialog, DialogFeedback, DialogTranscriptEmail
from tests.acceptance.fixtures import post_json
from tests.acceptance.harness import mark_acceptance


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEBUG=True,
)
class OnlineChatApiAcceptanceTest(TestCase):
    @mark_acceptance("CHAT-T-03")
    def test_widget_dialog_stores_first_and_last_name(self):
        client = Client()
        response = post_json(
            client,
            "/api/v1/online-chat/dialogs/",
            {
                "text": "Подскажите лимит снятия?",
                "widget_id": "site-belarusbank",
                "placement": "website",
                "first_name": "Анна",
                "last_name": "Козлова",
                "phone": "+375 29 123-45-67",
            },
        )
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertTrue(body["ok"])
        dialog = body["dialog"]
        self.assertEqual(dialog["client_first_name"], "Анна")
        self.assertEqual(dialog["client_last_name"], "Козлова")
        self.assertEqual(dialog["client_name"], "Анна Козлова")
        self.assertEqual(dialog["client_phone"], "+375291234567")
        self.assertEqual(dialog["status"], "waiting")
        self.assertGreaterEqual(len(dialog.get("messages") or []), 1)

        inbox = client.get("/api/v1/online-chat/dialogs/?status=waiting")
        self.assertEqual(inbox.status_code, 200)
        payload = inbox.json()
        self.assertGreaterEqual(payload["count"], 1)
        card = next(item for item in payload["items"] if item["id"] == dialog["id"])
        self.assertEqual(card["client_last_name"], "Козлова")
        self.assertIn("лимит", card["preview"].lower())

        accept = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog['id']}/accept/",
            {"operator_name": "Иванов И.И."},
        )
        self.assertEqual(accept.status_code, 200)
        self.assertEqual(accept.json()["dialog"]["status"], "active")

    @mark_acceptance("CHAT-T-06")
    def test_close_requires_topic_then_feedback_and_transcript(self):
        client = Client()
        created = post_json(
            client,
            "/api/v1/online-chat/dialogs/",
            {
                "text": "Как заблокировать карту?",
                "first_name": "Анна",
                "last_name": "Козлова",
                "phone": "+375 29 111-22-33",
            },
        )
        dialog_id = created.json()["dialog"]["id"]
        post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/accept/",
            {"operator_name": "Иванов И.И."},
        )
        post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/messages/",
            {"text": "Могу помочь с блокировкой.", "speaker": "operator"},
        )

        missing_topic = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/close/",
            {},
        )
        self.assertEqual(missing_topic.status_code, 400)

        closed = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/close/",
            {"topic": "Карты и счета"},
        )
        self.assertEqual(closed.status_code, 200)
        closed_body = closed.json()["dialog"]
        self.assertEqual(closed_body["status"], "closed")
        self.assertEqual(closed_body["close_topic"], "Карты и счета")
        self.assertIsNotNone(closed_body["closed_at"])

        dialog = Dialog.objects.get(pk=dialog_id)
        self.assertEqual(dialog.status, Dialog.Status.CLOSED)
        self.assertTrue(dialog.messages.filter(speaker="system").exists())

        feedback = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/feedback/",
            {"rating": 5, "comment": "Быстро помогли"},
        )
        self.assertEqual(feedback.status_code, 201)
        self.assertEqual(feedback.json()["feedback"]["rating"], 5)
        self.assertTrue(DialogFeedback.objects.filter(dialog_id=dialog_id).exists())

        mail.outbox.clear()
        transcript = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/send-transcript/",
            {"email": "anna@example.com"},
        )
        self.assertEqual(transcript.status_code, 201)
        payload = transcript.json()["transcript_email"]
        self.assertEqual(payload["status"], "sent")
        self.assertEqual(payload["email"], "anna@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("anna@example.com", mail.outbox[0].to)
        self.assertIn("Как заблокировать карту?", mail.outbox[0].body)
        self.assertIn("Могу помочь с блокировкой.", mail.outbox[0].body)
        self.assertIn("Карты и счета", mail.outbox[0].body)
        self.assertIn("Карты и счета", mail.outbox[0].subject)
        self.assertIn("Обращение: № ", mail.outbox[0].body)
        self.assertNotIn(f"Диалог: {dialog_id}", mail.outbox[0].body)
        self.assertTrue(
            DialogTranscriptEmail.objects.filter(
                dialog_id=dialog_id,
                status=DialogTranscriptEmail.Status.SENT,
            ).exists(),
        )

        # Client marks operator reply as read → 2 ticks for operator.
        mark_read = post_json(
            client,
            f"/api/v1/online-chat/dialogs/{dialog_id}/read/",
            {"reader": "client"},
        )
        self.assertEqual(mark_read.status_code, 200)
        read_body = mark_read.json()
        self.assertTrue(read_body["ok"])
        self.assertGreaterEqual(len(read_body["message_ids"]), 1)
        from online_chat.models import DialogMessage

        operator_msg = DialogMessage.objects.filter(
            dialog_id=dialog_id,
            speaker=DialogMessage.Speaker.OPERATOR,
        ).first()
        self.assertIsNotNone(operator_msg)
        assert operator_msg is not None
        self.assertEqual(operator_msg.receipt_status, DialogMessage.ReceiptStatus.READ)


if __name__ == "__main__":
    unittest.main()
