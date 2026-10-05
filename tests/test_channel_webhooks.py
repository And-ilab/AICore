import json
import os
import sys
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import Client, TestCase  # noqa: E402

from integrations.channels.webhooks import reset_inbox  # noqa: E402
from online_chat.models import ChannelConnection, Dialog, TelegramOnboardingSession  # noqa: E402


class ChannelWebhooksTest(TestCase):
    def setUp(self):
        reset_inbox()
        self.client = Client()

    def _tg(self, text: str, chat_id: int = 4242, update_id: int = 1):
        message = {
            "message_id": update_id * 10,
            "text": text,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "first_name": "Анна"},
        }
        if text.startswith("/"):
            token = text.split()[0]
            message["entities"] = [
                {"offset": 0, "length": len(token), "type": "bot_command"}
            ]
        return self.client.post(
            "/api/v1/channels/telegram/webhook/",
            data=json.dumps(
                {
                    "update_id": update_id,
                    "message": message,
                }
            ),
            content_type="application/json",
        )

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    def test_telegram_onboarding_then_queue(self, _send):
        start = self._tg("/start", update_id=1)
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json()["routed_to"], "onboarding")
        self.assertEqual(Dialog.objects.count(), 0)

        question = self._tg("Лимит снятия наличных?", update_id=2)
        self.assertEqual(question.status_code, 200)
        self.assertEqual(question.json()["routed_to"], "onboarding")
        self.assertEqual(Dialog.objects.count(), 0)

        fio = self._tg("Козлова Анна", update_id=3)
        self.assertEqual(fio.status_code, 200)
        self.assertEqual(fio.json()["routed_to"], "onboarding")

        phone = self._tg("80291234567", update_id=4)
        self.assertEqual(phone.status_code, 200)
        body = phone.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["routed_to"], "arm_queue")
        self.assertEqual(Dialog.objects.count(), 1)
        dialog = Dialog.objects.get()
        self.assertEqual(dialog.channel, "telegram")
        self.assertEqual(dialog.client_phone, "+375291234567")
        self.assertEqual(dialog.client_first_name, "Анна")
        self.assertEqual(dialog.client_last_name, "Козлова")
        self.assertIn("Лимит снятия", dialog.preview)
        session = TelegramOnboardingSession.objects.get(chat_id="4242")
        self.assertEqual(session.step, TelegramOnboardingSession.Step.DONE)

    def test_viber_webhook_message_and_handshake(self):
        handshake = self.client.post(
            "/api/v1/channels/viber/webhook/",
            data=json.dumps({"event": "webhook", "timestamp": 1}),
            content_type="application/json",
        )
        self.assertEqual(handshake.status_code, 200)
        self.assertEqual(handshake.json()["status"], 0)

        response = self.client.post(
            "/api/v1/channels/viber/webhook/",
            data=json.dumps(
                {
                    "event": "message",
                    "sender": {"id": "viber-user-1", "name": "Пётр"},
                    "message": {"type": "text", "text": "Не приходит SMS"},
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["channel"], "viber")
        self.assertEqual(body["routed_to"], "arm_queue")

    def test_widget_message_accepts_widget_id(self):
        response = self.client.post(
            "/api/v1/channels/widget/site-belarusbank/messages/",
            data=json.dumps(
                {
                    "text": "Здравствуйте",
                    "placement": "website",
                    "locale": "ru",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["widget_id"], "site-belarusbank")
        self.assertTrue(body["reply"])

        inbox = self.client.get("/api/v1/channels/inbox/")
        self.assertEqual(inbox.status_code, 200)
        self.assertGreaterEqual(inbox.json()["count"], 1)

    def test_vk_webhook_routes_message_to_dialog(self):
        response = self.client.post(
            "/api/v1/channels/vk/webhook/",
            data=json.dumps(
                {
                    "type": "message_new",
                    "event_id": "vk-event-1",
                    "object": {
                        "message": {
                            "peer_id": 777,
                            "text": "Вопрос из VK",
                        }
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Dialog.objects.filter(channel="vk", client_external_id="777").exists()
        )

    def test_ok_webhook_routes_message_to_dialog(self):
        response = self.client.post(
            "/api/v1/channels/ok/webhook/",
            data=json.dumps(
                {
                    "message": {
                        "sender_id": "ok-42",
                        "text": "Вопрос из OK",
                    }
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Dialog.objects.filter(channel="ok", client_external_id="ok-42").exists()
        )

    def test_signed_api_webhook_routes_message_to_dialog(self):
        response = self.client.post(
            "/api/v1/channels/api/webhook/",
            data=json.dumps(
                {
                    "client_external_id": "partner-client-1",
                    "text": "Вопрос из API",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Dialog.objects.filter(
                channel="api",
                client_external_id="partner-client-1",
            ).exists()
        )

    def _callback(self, chat_id: int = 4242, update_id: int = 50, data: str = "skip_field"):
        return self.client.post(
            "/api/v1/channels/telegram/webhook/",
            data=json.dumps(
                {
                    "update_id": update_id,
                    "callback_query": {
                        "id": f"cb-{update_id}",
                        "data": data,
                        "message": {"chat": {"id": chat_id, "type": "private"}},
                    },
                }
            ),
            content_type="application/json",
        )

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    @patch("online_chat.channel_delivery.answer_telegram_callback")
    def test_telegram_form_fields_order_and_optional_skip(self, _answer, send_mock):
        ChannelConnection.objects.create(
            channel=ChannelConnection.Channel.TELEGRAM,
            name="Telegram",
            is_active=True,
            config={
                "form_fields": [
                    {"key": "email", "label": "Email", "required": False, "type": "email"},
                    {"key": "name", "label": "Имя", "required": True, "type": "text"},
                    {"key": "phone", "label": "Телефон", "required": True, "type": "tel"},
                ]
            },
        )
        self.assertEqual(self._tg("/start", update_id=1).json()["routed_to"], "onboarding")
        question = self._tg("Лимит по карте", update_id=2)
        self.assertEqual(question.json()["field"], "email")
        markup = send_mock.call_args.kwargs.get("reply_markup") or {}
        self.assertIn("skip_field", json.dumps(markup))

        skip = self._callback(update_id=3)
        self.assertEqual(skip.json()["routed_to"], "onboarding")
        self.assertEqual(skip.json()["field"], "name")

        name = self._tg("Иванов Никита", update_id=4)
        self.assertEqual(name.json()["field"], "phone")
        phone = self._tg("+375291112233", update_id=5)
        self.assertEqual(phone.json()["routed_to"], "arm_queue")
        dialog = Dialog.objects.get()
        self.assertEqual(dialog.client_first_name, "Никита")
        self.assertEqual(dialog.client_last_name, "Иванов")
        self.assertEqual(dialog.client_phone, "+375291112233")

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    def test_telegram_start_restarts_while_previous_dialog_waiting(self, send_mock):
        self._tg("/start", update_id=1)
        self._tg("Первый вопрос", update_id=2)
        self._tg("Иванов Иван", update_id=3)
        queued = self._tg("+375291112233", update_id=4)
        self.assertEqual(queued.json()["routed_to"], "arm_queue")
        first = Dialog.objects.get()
        self.assertEqual(first.status, Dialog.Status.WAITING)

        start = self._tg("/start", update_id=5)
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json()["routed_to"], "onboarding")
        self.assertEqual(start.json()["step"], TelegramOnboardingSession.Step.AWAIT_QUESTION)
        client_texts = list(
            first.messages.filter(speaker="client").values_list("text", flat=True)
        )
        self.assertNotIn("/start", client_texts)
        greeting = send_mock.call_args[0][1]
        self.assertIn("вопрос", greeting.casefold())

        question = self._tg("Второй вопрос", update_id=6)
        self.assertEqual(question.json()["routed_to"], "onboarding")
        self.assertEqual(question.json()["field"], "name")
        self.assertEqual(Dialog.objects.count(), 1)
        first.refresh_from_db()
        first_texts = list(
            first.messages.filter(speaker="client").values_list("text", flat=True)
        )
        self.assertNotIn("Второй вопрос", first_texts)
        self.assertNotIn("/start", first_texts)

        self._tg("Петров Пётр", update_id=7)
        second = self._tg("+375299998877", update_id=8)
        self.assertEqual(second.json()["routed_to"], "arm_queue")
        self.assertEqual(Dialog.objects.count(), 2)

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    def test_telegram_start_without_entities_still_onboards(self, send_mock):
        response = self.client.post(
            "/api/v1/channels/telegram/webhook/",
            data=json.dumps(
                {
                    "update_id": 1,
                    "message": {
                        "message_id": 10,
                        "text": "/start",
                        "chat": {"id": 4242, "type": "private"},
                        "from": {"id": 4242, "first_name": "Анна"},
                    },
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["routed_to"], "onboarding")
        self.assertEqual(response.json()["step"], TelegramOnboardingSession.Step.AWAIT_QUESTION)
        greeting = send_mock.call_args[0][1]
        self.assertIn("вопрос", greeting.casefold())
        self.assertEqual(Dialog.objects.count(), 0)

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    def test_telegram_start_with_bot_username(self, send_mock):
        start = self._tg("/start@sufler_support_bot", update_id=1)
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json()["routed_to"], "onboarding")
        self.assertEqual(start.json()["step"], TelegramOnboardingSession.Step.AWAIT_QUESTION)
        greeting = send_mock.call_args[0][1]
        self.assertIn("вопрос", greeting.casefold())

    @patch("online_chat.telegram_onboarding.send_telegram_text")
    def test_telegram_commands_are_not_stored_in_open_dialog(self, _send):
        self._tg("/start", update_id=1)
        self._tg("Вопрос по карте", update_id=2)
        self._tg("Иванов Иван", update_id=3)
        queued = self._tg("+375291112233", update_id=4)
        self.assertEqual(queued.json()["routed_to"], "arm_queue")
        dialog = Dialog.objects.get()

        followup = self._tg("Уточнение по лимиту", update_id=5)
        self.assertEqual(followup.json()["routed_to"], "arm_queue")
        self.assertEqual(followup.json()["dialog_id"], str(dialog.id))

        ignored = self._tg("/help", update_id=6)
        self.assertEqual(ignored.json()["routed_to"], "command_ignored")
        start = self._tg("/start", update_id=7)
        self.assertEqual(start.json()["routed_to"], "onboarding")

        texts = list(
            dialog.messages.filter(speaker="client").values_list("text", flat=True)
        )
        self.assertIn("Вопрос по карте", texts)
        self.assertIn("Уточнение по лимиту", texts)
        self.assertNotIn("/help", texts)
        self.assertNotIn("/start", texts)
