from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django

django.setup()

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from online_chat.models import (
    BotConfiguration,
    Department,
    Dialog,
    DialogMessage,
    OperatorProfile,
    WidgetPlacement,
)
from online_chat.services import append_message, create_dialog_with_message, set_client_presence
from online_chat.tasks import classify_stale_dialogs
from sufler.asgi import application
from tests.acceptance.fixtures import post_json
from tests.acceptance.harness import mark_acceptance


@override_settings(DEBUG=True)
class ChatPlatformAcceptanceTest(TestCase):
    def setUp(self) -> None:
        self.client = Client()
        self.department = Department.objects.create(
            code="acceptance-support",
            name="Acceptance Support",
        )
        self.placement = WidgetPlacement.objects.create(
            widget_id="acceptance-widget",
            name="Acceptance Widget",
            department=self.department,
            allowed_domains=["testserver"],
            welcome_message="Здравствуйте!",
        )

    def operator(self, index: int, capacity: int = 1) -> OperatorProfile:
        operator = OperatorProfile.objects.create(
            external_id=f"acceptance-op-{index}",
            display_name=f"Оператор {index}",
            presence=OperatorProfile.Presence.ONLINE,
            max_active_dialogs=capacity,
        )
        operator.departments.add(self.department)
        return operator

    @mark_acceptance("CHAT-T-02")
    def test_auto_assignment_respects_operator_capacity(self):
        self.operator(1)
        self.operator(2)
        dialogs = [
            create_dialog_with_message(
                text=f"Обращение {index}",
                widget_id=self.placement.widget_id,
            )[0]
            for index in range(3)
        ]
        states = [Dialog.objects.get(pk=item.pk).status for item in dialogs]
        self.assertEqual(states.count(Dialog.Status.ACTIVE), 2)
        self.assertEqual(states.count(Dialog.Status.WAITING), 1)

    @mark_acceptance("CHAT-T-05")
    def test_sufler_permalink_is_removed_from_client_answer(self):
        operator = self.operator(1)
        dialog, _ = create_dialog_with_message(
            text="Как оформить карту?",
            widget_id=self.placement.widget_id,
        )
        response = post_json(
            self.client,
            f"/api/v1/online-chat/dialogs/{dialog.id}/messages/",
            {
                "speaker": "operator",
                "operator_name": operator.display_name,
                "response_origin": "sufler",
                "sufler_suggestion_text": (
                    "Оформите заявку. [Оформление карты]"
                    "(https://suz.local/articles/901)"
                ),
                "text": (
                    "Оформите заявку. [Оформление карты]"
                    "(https://suz.local/articles/901)"
                ),
            },
        )
        self.assertEqual(response.status_code, 201)
        text = response.json()["message"]["text"]
        self.assertNotIn("https://", text)
        message = DialogMessage.objects.get(pk=response.json()["message"]["id"])
        self.assertEqual(message.response_origin, "sufler")
        self.assertIn("suz.local", message.sufler_suggestion_text)

    @mark_acceptance("CHAT-T-07")
    def test_widget_placement_configuration_is_public(self):
        response = self.client.get(
            f"/api/v1/online-chat/config/widget/{self.placement.widget_id}/",
            HTTP_REFERER="http://testserver/page",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["config"]["welcome_message"], "Здравствуйте!")

    @mark_acceptance("CHAT-T-09")
    def test_supervisor_transfers_dialog(self):
        first = self.operator(1, capacity=2)
        second = self.operator(2, capacity=2)
        dialog, _ = create_dialog_with_message(
            text="Переведите меня",
            widget_id=self.placement.widget_id,
        )
        if dialog.operator_id != first.id:
            first, second = second, first
        response = post_json(
            self.client,
            f"/api/v1/online-chat/dialogs/{dialog.id}/transfer/",
            {"operator_id": str(second.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dialog"]["operator_id"], str(second.id))

    @mark_acceptance("CHAT-T-10")
    @mark_acceptance("CHAT-T-16")
    def test_first_line_bot_and_handoff(self):
        self.operator(1)
        BotConfiguration.objects.create(
            name="FAQ",
            department=self.department,
            is_active=True,
            welcome_message="Я виртуальный помощник.",
            trigger_responses={"карт": "Уточните вопрос по карте."},
            max_bot_turns=3,
            handoff_message="Передаю оператору.",
        )
        dialog, _ = create_dialog_with_message(
            text="Здравствуйте",
            widget_id=self.placement.widget_id,
        )
        append_message(
            dialog,
            speaker=DialogMessage.Speaker.CLIENT,
            text="Вопрос по карте",
        )
        append_message(
            dialog,
            speaker=DialogMessage.Speaker.CLIENT,
            text="Нужен человек",
        )
        dialog.refresh_from_db()
        self.assertFalse(dialog.bot_active)
        self.assertTrue(dialog.operator_id)

    @mark_acceptance("CHAT-T-11")
    def test_supervisor_overview_uses_live_database(self):
        create_dialog_with_message(
            text="Жду ответа",
            widget_id=self.placement.widget_id,
        )
        response = self.client.get("/api/v1/online-chat/supervisor/overview/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["waiting"], 1)

    @mark_acceptance("CHAT-T-12")
    def test_telegram_webhook_creates_arm_dialog(self):
        from unittest.mock import patch

        def _post(text: str, update_id: int):
            return self.client.post(
                "/api/v1/channels/telegram/webhook/",
                data=json.dumps(
                    {
                        "update_id": update_id,
                        "message": {
                            "text": text,
                            "chat": {"id": 4242},
                        },
                    }
                ),
                content_type="application/json",
            )

        with patch("online_chat.telegram_onboarding.send_telegram_text"):
            self.assertEqual(_post("/start", 100).status_code, 200)
            self.assertEqual(_post("Вопрос из Telegram", 101).status_code, 200)
            self.assertEqual(_post("Иванов Иван", 102).status_code, 200)
            response = _post("+375291112233", 103)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["routed_to"], "arm_queue")
        self.assertTrue(
            Dialog.objects.filter(
                channel="telegram",
                client_external_id="4242",
            ).exists()
        )

    @mark_acceptance("CHAT-T-13")
    def test_cross_dialog_history_by_phone(self):
        for text in ("Первый вопрос", "Повторный вопрос"):
            create_dialog_with_message(
                text=text,
                widget_id=self.placement.widget_id,
                client_phone="+375 29 111-22-33",
            )
        response = self.client.get(
            "/api/v1/online-chat/history/",
            {"phone": "375291112233"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 2)

    @mark_acceptance("CHAT-T-14")
    def test_period_analytics_uses_persisted_dialogs(self):
        dialog, _ = create_dialog_with_message(
            text="Отчётное обращение",
            widget_id=self.placement.widget_id,
        )
        dialog.status = Dialog.Status.CLOSED
        dialog.closed_at = timezone.now()
        dialog.save(update_fields=["status", "closed_at", "updated_at"])
        response = self.client.get(
            "/api/v1/online-chat/analytics/",
            {"period": "week"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["dialogs"], 1)
        self.assertEqual(response.json()["kpis"]["closed"], 1)

    @mark_acceptance("CHAT-T-15")
    def test_offline_client_receives_preserved_message_on_return(self):
        dialog, _ = create_dialog_with_message(
            text="Ухожу со страницы",
            widget_id=self.placement.widget_id,
        )
        set_client_presence(dialog, online=False)
        append_message(
            dialog,
            speaker=DialogMessage.Speaker.OPERATOR,
            text="Ответ сохранён",
        )
        set_client_presence(dialog, online=True)
        response = self.client.get(f"/api/v1/online-chat/dialogs/{dialog.id}/")
        texts = [item["text"] for item in response.json()["dialog"]["messages"]]
        self.assertIn("Ответ сохранён", texts)

    @mark_acceptance("CHAT-T-17")
    def test_colleague_dialog_is_read_only(self):
        owner = self.operator(1)
        colleague = self.operator(2)
        dialog, _ = create_dialog_with_message(
            text="Диалог владельца",
            widget_id=self.placement.widget_id,
        )
        self.assertEqual(dialog.operator_id, owner.id)
        read = self.client.get(f"/api/v1/online-chat/dialogs/{dialog.id}/")
        self.assertEqual(read.status_code, 200)
        write = post_json(
            self.client,
            f"/api/v1/online-chat/dialogs/{dialog.id}/messages/",
            {
                "speaker": "operator",
                "operator_name": colleague.display_name,
                "text": "Не должен отправиться",
            },
        )
        self.assertEqual(write.status_code, 403)

    @mark_acceptance("CHAT-T-19")
    def test_blocked_client_cannot_start_another_dialog(self):
        dialog, _ = create_dialog_with_message(
            text="Первое обращение",
            widget_id=self.placement.widget_id,
            client_phone="+375 29 555-55-55",
        )
        blocked = post_json(
            self.client,
            f"/api/v1/online-chat/dialogs/{dialog.id}/block/",
            {"reason": "abuse"},
        )
        self.assertEqual(blocked.status_code, 200)
        retry = post_json(
            self.client,
            "/api/v1/online-chat/dialogs/",
            {
                "text": "Повтор",
                "widget_id": self.placement.widget_id,
                "phone": "+375295555555",
            },
        )
        self.assertEqual(retry.status_code, 403)

    @mark_acceptance("CHAT-T-20")
    def test_offline_dialog_is_classified_lost(self):
        dialog, _ = create_dialog_with_message(
            text="Клиент пропал",
            widget_id=self.placement.widget_id,
        )
        set_client_presence(dialog, online=False)
        Dialog.objects.filter(pk=dialog.pk).update(
            client_last_seen_at=timezone.now() - timedelta(minutes=20)
        )
        with override_settings(ONLINE_CHAT_LOST_TIMEOUT_SECONDS=60):
            classify_stale_dialogs()
        dialog.refresh_from_db()
        self.assertEqual(dialog.outcome, Dialog.Outcome.LOST)


@override_settings(
    CHANNEL_LAYERS={
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
)
class ChatTypingAcceptanceTest(TransactionTestCase):
    @mark_acceptance("CHAT-T-18")
    def test_typing_events_are_delivered_to_arm(self):
        dialog = Dialog.objects.create(
            status=Dialog.Status.WAITING,
            client_first_name="Typing",
        )

        async def scenario() -> None:
            arm = WebsocketCommunicator(application, "/ws/online-chat/arm/")
            widget = WebsocketCommunicator(
                application,
                f"/ws/online-chat/dialog/{dialog.id}/",
            )
            arm_connected, _ = await arm.connect()
            widget_connected, _ = await widget.connect()
            self.assertTrue(arm_connected)
            self.assertTrue(widget_connected)
            await arm.receive_json_from()
            await widget.receive_json_from()
            await widget.send_json_to(
                {
                    "type": "typing.start",
                    "speaker": "client",
                    "draft": "Печатаю ответ",
                }
            )
            event = await arm.receive_json_from()
            while event["type"] != "typing.start":
                event = await arm.receive_json_from()
            self.assertEqual(event["type"], "typing.start")
            self.assertEqual(event["payload"]["dialog_id"], str(dialog.id))
            self.assertEqual(event["payload"]["speaker"], "client")
            await widget.disconnect()
            await arm.disconnect()

        async_to_sync(scenario)()
