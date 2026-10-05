from __future__ import annotations

import json
import tempfile
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from online_chat.models import (
    BaseMessage,
    BotConfiguration,
    Department,
    Dialog,
    DialogMessage,
    OperatorPresenceLog,
    OperatorProfile,
    RoutingRule,
    WidgetPlacement,
)
from online_chat.routing_services import (
    accept_waiting_dialog,
    auto_assign_dialog,
    select_department,
    update_operator_presence,
)
from online_chat.services import (
    append_message,
    create_dialog_with_message,
    set_client_presence,
)
from online_chat.tasks import classify_stale_dialogs, send_hold_base_message


class RoutingTests(TestCase):
    def setUp(self) -> None:
        self.sales = Department.objects.create(code="sales", name="Sales", priority=20)
        self.support = Department.objects.create(code="support", name="Support", priority=10)
        self.placement = WidgetPlacement.objects.create(
            widget_id="site-main", name="Main", department=self.support
        )

    def operator(self, name: str, capacity: int = 2) -> OperatorProfile:
        item = OperatorProfile.objects.create(
            external_id=name.lower(),
            display_name=name,
            presence=OperatorProfile.Presence.ONLINE,
            max_active_dialogs=capacity,
        )
        item.departments.add(self.support)
        return item

    def test_rule_overrides_placement_department(self) -> None:
        RoutingRule.objects.create(
            name="VIP", priority=1, placement=self.placement,
            department=self.sales, conditions={"segment": "vip"}
        )
        department, _, reason = select_department(
            widget_id="site-main", context={"segment": "vip"}
        )
        self.assertEqual(department, self.sales)
        self.assertEqual(reason, "routing_rule:VIP")

    def test_least_active_operator_and_capacity(self) -> None:
        first = self.operator("First", capacity=1)
        second = self.operator("Second", capacity=2)
        Dialog.objects.create(
            status=Dialog.Status.ACTIVE, department=self.support,
            operator=second, operator_name=second.display_name
        )
        waiting = Dialog.objects.create(status=Dialog.Status.WAITING, department=self.support)
        assigned = auto_assign_dialog(waiting)
        self.assertEqual(assigned.operator, first)
        another = Dialog.objects.create(status=Dialog.Status.WAITING, department=self.support)
        self.assertEqual(auto_assign_dialog(another).operator, second)

    def test_presence_online_reruns_queue(self) -> None:
        operator = self.operator("Away")
        operator.presence = OperatorProfile.Presence.OFFLINE
        operator.save()
        dialog = Dialog.objects.create(status=Dialog.Status.WAITING, department=self.support)
        update_operator_presence(operator, OperatorProfile.Presence.ONLINE)
        dialog.refresh_from_db()
        self.assertEqual(dialog.operator, operator)

    def test_presence_change_writes_history_log(self) -> None:
        operator = self.operator("Logged")
        update_operator_presence(operator, OperatorProfile.Presence.LUNCH)
        update_operator_presence(operator, OperatorProfile.Presence.ONLINE)
        logs = list(OperatorPresenceLog.objects.filter(operator=operator).order_by("started_at"))
        self.assertGreaterEqual(len(logs), 2)
        self.assertEqual(logs[-1].presence, OperatorProfile.Presence.ONLINE)
        self.assertIsNone(logs[-1].ended_at)
        self.assertIsNotNone(logs[-2].ended_at)

    def test_double_acceptance_is_rejected(self) -> None:
        first = self.operator("First")
        second = self.operator("Second")
        dialog = Dialog.objects.create(status=Dialog.Status.WAITING, department=self.support)
        accept_waiting_dialog(dialog.id, operator=first)
        with self.assertRaisesMessage(ValueError, "dialog is not waiting"):
            accept_waiting_dialog(dialog.id, operator=second)
        dialog.refresh_from_db()
        self.assertEqual(dialog.operator, first)


class ApiTests(TestCase):
    def setUp(self) -> None:
        self.department = Department.objects.create(code="support", name="Support")
        self.placement = WidgetPlacement.objects.create(
            widget_id="public-widget",
            name="Public",
            department=self.department,
            welcome_message="Hello",
            config={"language": "en"},
        )

    def test_operator_photo_endpoint_and_message_avatar(self) -> None:
        from online_chat.services import (
            accept_dialog,
            create_dialog_with_message,
            serialize_dialog,
            serialize_message,
            serialize_messages_for_dialog,
        )
        from online_chat.views import _normalize_photo_url

        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        operator = OperatorProfile.objects.create(
            external_id="avatar-op",
            display_name="Иванов И.И.",
            is_active=True,
            photo_url=_normalize_photo_url(f"data:image/png;base64,{png}"),
        )
        dialog, _ = create_dialog_with_message(
            text="Вопрос",
            widget_id=self.placement.widget_id,
            client_first_name="А",
            client_last_name="Б",
            client_phone="+375291111111",
        )
        accept_dialog(dialog, operator.display_name)
        dialog.refresh_from_db()
        message = append_message(
            dialog,
            speaker=DialogMessage.Speaker.OPERATOR,
            text="Ответ",
        )
        payload = serialize_message(
            message,
            operator_name=dialog.operator_name,
            operator_id=str(operator.id),
            operator_avatar=operator.photo_url,
        )
        photo_path = f"/api/v1/online-chat/operators/{operator.id}/photo/"
        self.assertEqual(payload.get("operator_id"), str(operator.id))
        self.assertEqual(payload.get("operator_avatar"), photo_path)
        self.assertFalse(str(payload["operator_avatar"]).startswith("data:"))

        dialog_payload = serialize_dialog(dialog)
        self.assertEqual(dialog_payload.get("operator_id"), str(operator.id))
        self.assertEqual(dialog_payload.get("operator_avatar"), photo_path)

        history = serialize_messages_for_dialog(dialog, [message])
        self.assertEqual(history[0].get("operator_id"), str(operator.id))
        self.assertEqual(history[0].get("operator_avatar"), photo_path)

        nameless = serialize_message(
            message,
            operator_name="Другое имя",
            operator_id="",
            operator_avatar=photo_path,
        )
        self.assertEqual(nameless.get("operator_avatar"), photo_path)

        dialog.operator_name = "Другое имя"
        dialog.save(update_fields=["operator_name"])
        mismatched = serialize_messages_for_dialog(
            dialog,
            [message],
            timeline=[(message.created_at, "Другое имя")],
        )
        self.assertEqual(mismatched[0].get("operator_id"), str(operator.id))
        self.assertEqual(mismatched[0].get("operator_avatar"), photo_path)

        photo = self.client.get(
            reverse("online_chat_operator_photo", args=[operator.id]),
        )
        self.assertEqual(photo.status_code, 200)
        self.assertTrue(photo["Content-Type"].startswith("image/"))
        self.assertEqual(photo["Access-Control-Allow-Origin"], "*")
        self.assertEqual(photo["Cross-Origin-Resource-Policy"], "cross-origin")
        self.assertGreater(len(photo.content), 0)

        operator.is_active = False
        operator.save(update_fields=["is_active"])
        inactive_photo = self.client.get(
            reverse("online_chat_operator_photo", args=[operator.id]),
        )
        self.assertEqual(inactive_photo.status_code, 200)

        response = self.client.get(
            reverse("online_chat_widget_config", args=[self.placement.widget_id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["config"]["welcome_message"], "Hello")

    @override_settings(DEBUG=True)
    def test_operator_can_upload_own_photo(self) -> None:
        from django.contrib.auth import get_user_model

        png = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        )
        operator = OperatorProfile.objects.create(
            external_id="op-self",
            display_name="Самостоятельный",
            is_active=True,
        )
        user = get_user_model().objects.create_user(username="op-self", password="x")
        self.client.force_login(user)
        response = self.client.patch(
            reverse("online_chat_operator_me_photo"),
            data=json.dumps({"photo_url": f"data:image/png;base64,{png}"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        operator.refresh_from_db()
        self.assertTrue(operator.photo_url.startswith("data:image/"))
        photo = self.client.get(reverse("online_chat_operator_photo", args=[operator.id]))
        self.assertEqual(photo.status_code, 200)
        me = self.client.get(reverse("online_chat_operator_me"))
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["operator"]["id"], str(operator.id))

    @override_settings(DEBUG=True)
    def test_supervisor_kpis(self) -> None:
        Dialog.objects.create(status=Dialog.Status.WAITING, department=self.department)
        Dialog.objects.create(status=Dialog.Status.ACTIVE, department=self.department)
        response = self.client.get(reverse("online_chat_supervisor"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["kpis"]["waiting"], 1)
        self.assertEqual(response.json()["kpis"]["active"], 1)

    @override_settings(DEBUG=True)
    def test_seed_returns_active_and_waiting_summary(self) -> None:
        response = self.client.post(
            reverse("online_chat_dev_seed"),
            data=json.dumps({
                "operators": 1, "clients": 5, "messages_per_dialog": 2,
                "auto_assign": True, "reset": True,
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        summary = response.json()["summary"]
        self.assertEqual(summary["dialogs"], 5)
        self.assertEqual(summary["messages"], 10)
        self.assertEqual(summary["active"], 3)
        self.assertEqual(summary["waiting"], 2)

    @override_settings(DEBUG=False)
    def test_seed_is_hidden_outside_debug(self) -> None:
        response = self.client.post(
            reverse("online_chat_dev_seed"), data="{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 404)

    def test_create_dialog_uses_placement_and_routing(self) -> None:
        dialog, _ = create_dialog_with_message(text="Help", widget_id="public-widget")
        self.assertEqual(dialog.department, self.department)
        self.assertEqual(dialog.routing_reason, "placement:public-widget")

    @override_settings(DEBUG=True)
    def test_management_aliases_match_spa_contract(self) -> None:
        response = self.client.post(
            reverse("online_chat_operators"),
            data=json.dumps(
                {
                    "name": "Иванов И.И.",
                    "username": "ivanov",
                    "capacity": 4,
                    "department_id": str(self.department.id),
                    "presence": "online",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        operator = response.json()["operator"]
        self.assertEqual(operator["name"], "Иванов И.И.")
        self.assertEqual(operator["username"], "ivanov")
        self.assertEqual(operator["capacity"], 4)
        self.assertEqual(operator["department_id"], str(self.department.id))

    def test_client_history_links_dialogs_by_phone(self) -> None:
        create_dialog_with_message(
            text="Первое обращение",
            widget_id="public-widget",
            client_phone="+375 29 111-22-33",
            client_first_name="Анна",
            client_last_name="Козлова",
        )
        current, _ = create_dialog_with_message(
            text="Повторное обращение",
            widget_id="public-widget",
            client_phone="375291112233",
            client_first_name="Анна",
            client_last_name="Козлова",
        )
        response = self.client.get(
            reverse("online_chat_client_history"),
            {"dialog_id": str(current.id)},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["previous_count"], 1)
        self.assertFalse(body["is_first"])
        self.assertNotIn("Первое обращение клиента", body["summary"])

    def test_client_history_does_not_link_different_phones(self) -> None:
        create_dialog_with_message(
            text="Лимит по карте",
            widget_id="public-widget",
            client_phone="+375291234567",
            client_first_name="Никита",
            client_last_name="Краснов",
        )
        current, _ = create_dialog_with_message(
            text="Повторно про лимит",
            widget_id="public-widget",
            client_phone="+375291234967",
            client_first_name="краснов",
            client_last_name="никита",
        )
        response = self.client.get(
            reverse("online_chat_client_history"),
            {"dialog_id": str(current.id)},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["previous_count"], 0)
        self.assertTrue(body["is_first"])

    def test_offline_dialog_becomes_lost_after_timeout(self) -> None:
        dialog, _ = create_dialog_with_message(
            text="Нет ответа",
            widget_id="public-widget",
        )
        set_client_presence(dialog, online=False)
        Dialog.objects.filter(pk=dialog.pk).update(
            client_last_seen_at=timezone.now() - timedelta(minutes=20)
        )
        with override_settings(ONLINE_CHAT_LOST_TIMEOUT_SECONDS=60):
            result = classify_stale_dialogs()
        dialog.refresh_from_db()
        self.assertEqual(result["classified_lost"], 1)
        self.assertEqual(dialog.outcome, Dialog.Outcome.LOST)

    def test_attachment_upload_uses_object_store(self) -> None:
        dialog, _ = create_dialog_with_message(
            text="Отправлю документ",
            widget_id="public-widget",
        )
        with tempfile.TemporaryDirectory() as root:
            with override_settings(
                ONLINE_CHAT_OBJECT_STORE_BACKEND="fs",
                ONLINE_CHAT_OBJECT_STORE_ROOT=root,
                ONLINE_CHAT_MAX_UPLOAD_BYTES=1024,
                ONLINE_CHAT_ALLOWED_UPLOAD_TYPES=("text/plain",),
                DEBUG=True,
            ):
                response = self.client.post(
                    reverse("online_chat_dialog_attachment_upload", args=[dialog.id]),
                    {
                        "speaker": "client",
                        "file": SimpleUploadedFile(
                            "note.txt",
                            b"test attachment",
                            content_type="text/plain",
                        ),
                    },
                )
        self.assertEqual(response.status_code, 201)
        message = DialogMessage.objects.get(pk=response.json()["message"]["id"])
        self.assertEqual(message.attachment_name, "note.txt")
        self.assertEqual(message.attachment_scan_status, "clean")

    def test_first_line_bot_replies_then_hands_off(self) -> None:
        BotConfiguration.objects.create(
            name="FAQ",
            department=self.department,
            is_active=True,
            welcome_message="Я виртуальный помощник.",
            trigger_responses={"карт": "Какой вопрос по карте?"},
            max_bot_turns=3,
            handoff_message="Передаю оператору.",
        )
        dialog, _ = create_dialog_with_message(
            text="Здравствуйте",
            widget_id="public-widget",
        )
        self.assertTrue(
            dialog.bot_active,
            (dialog.bot_turns, list(dialog.messages.values_list("speaker", "text"))),
        )
        append_message(
            dialog,
            speaker=DialogMessage.Speaker.CLIENT,
            text="Вопрос по карте",
        )
        dialog.refresh_from_db()
        self.assertTrue(
            dialog.bot_active,
            (dialog.bot_turns, list(dialog.messages.values_list("speaker", "text"))),
        )
        self.assertTrue(
            dialog.messages.filter(
                speaker=DialogMessage.Speaker.BOT,
                text="Какой вопрос по карте?",
            ).exists()
        )
        append_message(
            dialog,
            speaker=DialogMessage.Speaker.CLIENT,
            text="Другой вопрос",
        )
        dialog.refresh_from_db()
        self.assertFalse(dialog.bot_active)
        self.assertTrue(
            dialog.messages.filter(
                speaker=DialogMessage.Speaker.BOT,
                text="Передаю оператору.",
            ).exists()
        )

    def test_base_message_before_bot_matches_widget_placement(self) -> None:
        BaseMessage.objects.create(
            title="Welcome",
            text="Базовое приветствие",
            channels=[f"widget:{self.placement.id}"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            sort_order=10,
        )
        BaseMessage.objects.create(
            title="Other",
            text="Чужое приветствие",
            channels=["widget:00000000-0000-0000-0000-000000000000"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            sort_order=20,
        )

        dialog, _ = create_dialog_with_message(text="Help", widget_id="public-widget")

        self.assertTrue(dialog.messages.filter(text="Базовое приветствие").exists())
        self.assertFalse(dialog.messages.filter(text="Чужое приветствие").exists())

    def test_dialog_create_response_contains_base_messages_for_widget(self) -> None:
        BaseMessage.objects.create(
            title="Welcome",
            text="Базовое приветствие",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            sort_order=1,
        )
        response = self.client.post(
            reverse("online_chat_dialogs"),
            data=json.dumps(
                {
                    "text": "Здравствуйте",
                    "widget_id": "public-widget",
                    "placement": "website",
                    "channel": "widget",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()["dialog"]["messages"]
        texts = [item["text"] for item in payload]
        self.assertIn("Базовое приветствие", texts)

    def test_offline_base_messages_only_sent_when_line_closed(self) -> None:
        from online_chat.models import WorkScheduleSettings

        BaseMessage.objects.create(
            title="Online only",
            text="Онлайн-приветствие",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            sort_order=1,
        )
        BaseMessage.objects.create(
            title="Offline notice",
            text="Сейчас мы вне графика",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.OFFLINE,
            sort_order=2,
        )
        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])

        dialog, _ = create_dialog_with_message(text="Есть вопрос", widget_id="public-widget")
        texts = list(dialog.messages.values_list("text", flat=True))
        self.assertIn("Сейчас мы вне графика", texts)
        self.assertNotIn("Онлайн-приветствие", texts)

    def test_base_message_before_bot_sent_for_telegram_channel(self) -> None:
        BaseMessage.objects.create(
            title="TG welcome",
            text="Приветствие Telegram",
            channels=["telegram"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            sort_order=1,
        )
        dialog, _ = create_dialog_with_message(
            text="Привет из TG",
            channel="telegram",
            widget_id="",
            placement="telegram",
            client_external_id="tg-1",
        )
        self.assertTrue(dialog.messages.filter(text="Приветствие Telegram").exists())

    def test_hold_base_message_is_scheduled_with_delay(self) -> None:
        message = BaseMessage.objects.create(
            title="Ожидание оператора",
            text="Ожидайте ответа оператора",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=7,
            sort_order=1,
        )
        with patch(
            "online_chat.tasks.send_hold_base_message.apply_async"
        ) as mocked_async:
            dialog, _ = create_dialog_with_message(
                text="Здравствуйте",
                widget_id="public-widget",
                channel="widget",
            )
        self.assertFalse(dialog.messages.filter(text=message.text).exists())
        mocked_async.assert_called_once()
        self.assertEqual(mocked_async.call_args.kwargs.get("countdown"), 7)

    def test_hold_base_message_delivered_while_waiting(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])
        base = BaseMessage.objects.create(
            title="Ожидание оператора",
            text="Ожидайте ответа оператора",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=0,
            sort_order=1,
        )
        dialog, _ = create_dialog_with_message(
            text="Первое сообщение",
            widget_id="public-widget",
            channel="widget",
            skip_auto_assign=True,
        )
        self.assertEqual(dialog.status, Dialog.Status.WAITING)
        self.assertTrue(
            dialog.messages.filter(text=base.text, speaker=DialogMessage.Speaker.BOT).exists()
        )
        result = send_hold_base_message(str(dialog.id), str(base.id))
        self.assertFalse(result["sent"])
        self.assertEqual(result["reason"], "already_sent")

    def test_hold_base_message_in_dialog_create_http_payload(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])
        BaseMessage.objects.create(
            title="Ожидание оператора",
            text="Ожидайте ответа оператора",
            channels=[f"widget:{self.placement.id}"],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=0,
            sort_order=1,
        )
        response = self.client.post(
            reverse("online_chat_dialogs"),
            data=json.dumps(
                {
                    "text": "Здравствуйте",
                    "widget_id": "public-widget",
                    "placement": "website",
                    "channel": "widget",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        texts = [item["text"] for item in response.json()["dialog"]["messages"]]
        self.assertIn("Ожидайте ответа оператора", texts)

    def test_custom_offline_message_matches_widget_placement(self) -> None:
        from online_chat.models import WorkScheduleSettings

        BaseMessage.objects.create(
            title="Offline custom",
            text="Кастомное вне графика",
            channels=[f"widget:{self.placement.id}"],
            send_phase=BaseMessage.SendPhase.OFFLINE,
            sort_order=2,
        )
        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])

        dialog, _ = create_dialog_with_message(
            text="Есть вопрос",
            widget_id="public-widget",
            skip_auto_assign=True,
        )
        texts = list(dialog.messages.values_list("text", flat=True))
        self.assertIn("Кастомное вне графика", texts)

    def test_offline_then_online_resends_hold_message(self) -> None:
        from online_chat.models import WorkScheduleSettings
        from online_chat.routing_services import close_working_day, open_working_day

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])
        BaseMessage.objects.create(
            title="Hold",
            text="Ждите оператора",
            channels=[],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=0,
            sort_order=1,
        )
        BaseMessage.objects.create(
            title="Offline",
            text="Линия закрыта",
            channels=[],
            send_phase=BaseMessage.SendPhase.OFFLINE,
            delay_seconds=0,
            sort_order=2,
        )
        dialog, _ = create_dialog_with_message(
            text="Первое",
            widget_id="public-widget",
            skip_auto_assign=True,
        )
        self.assertTrue(dialog.messages.filter(text="Ждите оператора").exists())

        close_working_day()
        dialog.refresh_from_db()
        self.assertEqual(dialog.outcome, Dialog.Outcome.OFFLINE)
        self.assertTrue(dialog.messages.filter(text="Линия закрыта").exists())

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])
        open_working_day()
        hold_count = dialog.messages.filter(
            text="Ждите оператора",
            speaker=DialogMessage.Speaker.BOT,
        ).count()
        self.assertGreaterEqual(hold_count, 2)

    def test_offline_then_hold_sent_while_line_closed(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])
        BaseMessage.objects.create(
            title="Offline",
            text="Линия закрыта",
            channels=[],
            send_phase=BaseMessage.SendPhase.OFFLINE,
            delay_seconds=0,
            sort_order=1,
        )
        BaseMessage.objects.create(
            title="Hold",
            text="Ждите оператора",
            channels=[],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=0,
            sort_order=2,
        )
        dialog, _ = create_dialog_with_message(
            text="Первое",
            widget_id="public-widget",
            skip_auto_assign=True,
        )
        texts = list(
            dialog.messages.order_by("created_at").values_list("text", flat=True)
        )
        self.assertIn("Линия закрыта", texts)
        self.assertIn("Ждите оператора", texts)
        self.assertLess(texts.index("Линия закрыта"), texts.index("Ждите оператора"))

    def test_offline_and_before_bot_delays_are_scheduled(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])
        offline = BaseMessage.objects.create(
            title="Offline",
            text="Позже ответим",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.OFFLINE,
            delay_seconds=5,
            sort_order=1,
        )
        hold = BaseMessage.objects.create(
            title="Hold",
            text="Ждите оператора",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=3,
            sort_order=2,
        )
        with (
            patch("online_chat.tasks.send_delayed_base_message.apply_async") as delayed_async,
            patch("online_chat.tasks.send_hold_base_message.apply_async") as hold_async,
        ):
            dialog, _ = create_dialog_with_message(
                text="Вопрос",
                widget_id="public-widget",
                skip_auto_assign=True,
            )
        self.assertFalse(dialog.messages.filter(text=offline.text).exists())
        self.assertFalse(dialog.messages.filter(text=hold.text).exists())
        delayed_async.assert_called_once()
        self.assertEqual(delayed_async.call_args.kwargs.get("countdown"), 5)
        hold_async.assert_called_once()
        self.assertEqual(hold_async.call_args.kwargs.get("countdown"), 8)

    def test_before_bot_delay_is_scheduled(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])
        welcome = BaseMessage.objects.create(
            title="Welcome",
            text="Привет с задержкой",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.BEFORE_BOT,
            delay_seconds=4,
            sort_order=1,
        )
        with patch(
            "online_chat.tasks.send_delayed_base_message.apply_async"
        ) as delayed_async:
            dialog, _ = create_dialog_with_message(
                text="Вопрос",
                widget_id="public-widget",
                skip_auto_assign=True,
            )
        self.assertFalse(dialog.messages.filter(text=welcome.text).exists())
        delayed_async.assert_called_once()
        self.assertEqual(delayed_async.call_args.kwargs.get("countdown"), 4)

    def test_hold_base_message_sends_while_offline_waiting(self) -> None:
        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])
        hold = BaseMessage.objects.create(
            title="Hold",
            text="Ждите даже офлайн",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.HOLD,
            delay_seconds=0,
            sort_order=1,
        )
        dialog, _ = create_dialog_with_message(
            text="Вопрос",
            widget_id="public-widget",
            skip_auto_assign=True,
        )
        self.assertEqual(dialog.outcome, Dialog.Outcome.OFFLINE)
        self.assertTrue(
            dialog.messages.filter(text=hold.text, speaker=DialogMessage.Speaker.BOT).exists()
        )

    def test_dialogs_collection_filters_by_client_ip_and_rating(self) -> None:
        first, _ = create_dialog_with_message(
            text="Первый диалог",
            widget_id="public-widget",
            channel="widget",
            client_ip="10.10.10.1",
            skip_auto_assign=True,
        )
        second, _ = create_dialog_with_message(
            text="Второй диалог",
            widget_id="public-widget",
            channel="widget",
            client_ip="10.10.10.2",
            skip_auto_assign=True,
        )
        from online_chat.services import save_feedback

        save_feedback(first, rating=5, comment="")
        save_feedback(second, rating=3, comment="")
        response = self.client.get(
            reverse("online_chat_dialogs"),
            {"status": Dialog.Status.WAITING, "client_ip": "10.10.10.1", "ratings": "5"},
        )
        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(first.id))
        self.assertEqual(items[0].get("client_ip"), "10.10.10.1")
        self.assertEqual(items[0].get("feedback_rating"), 5)

    def test_global_bot_sends_after_bot_message_before_handoff(self) -> None:
        BotConfiguration.objects.create(
            name="Global FAQ",
            is_active=True,
            handoff_message="Передаю оператору.",
        )
        BaseMessage.objects.create(
            title="Escalation",
            text="Срочное уведомление",
            channels=["widget"],
            send_phase=BaseMessage.SendPhase.AFTER_BOT,
            sort_order=10,
        )
        dialog, _ = create_dialog_with_message(text="Help", widget_id="public-widget")

        append_message(dialog, speaker=DialogMessage.Speaker.CLIENT, text="Не знаю")

        bot_texts = list(
            dialog.messages.filter(speaker=DialogMessage.Speaker.BOT)
            .order_by("created_at")
            .values_list("text", flat=True)
        )
        self.assertEqual(bot_texts[-2:], ["Срочное уведомление", "Передаю оператору."])


class FormFieldsAndHistoryTests(TestCase):
    def setUp(self) -> None:
        self.department = Department.objects.create(code="support", name="Support")
        self.placement = WidgetPlacement.objects.create(
            widget_id="public-widget",
            name="Public",
            department=self.department,
            form_fields=[
                {"key": "name", "label": "Имя", "required": True, "type": "text"},
                {"key": "phone", "label": "Телефон", "required": False, "type": "tel"},
            ],
        )

    def test_normalize_form_fields_keeps_admin_order_and_required(self) -> None:
        from online_chat.models import normalize_form_fields

        fields = normalize_form_fields(
            [
                {"key": "email", "label": "Email", "required": False, "type": "email"},
                {"key": "name", "label": "Имя", "required": False, "type": "text"},
                {"key": "phone", "label": "Телефон", "required": True, "type": "tel"},
            ]
        )
        self.assertEqual([item["key"] for item in fields], ["email", "name", "phone"])
        self.assertFalse(fields[0]["required"])
        self.assertFalse(fields[1]["required"])
        self.assertTrue(fields[2]["required"])
        self.assertNotIn("last_name", [item["key"] for item in fields])

    def test_widget_config_returns_only_configured_fields(self) -> None:
        response = self.client.get(
            reverse("online_chat_widget_config", args=[self.placement.widget_id])
        )
        self.assertEqual(response.status_code, 200)
        fields = response.json()["config"]["form_fields"]
        self.assertEqual([item["key"] for item in fields], ["name", "phone"])
        self.assertTrue(fields[0]["required"])
        self.assertFalse(fields[1]["required"])

    def test_operator_sees_cross_channel_history_client_does_not(self) -> None:
        first, first_msg = create_dialog_with_message(
            text="Старый вопрос из виджета",
            widget_id="public-widget",
            channel="widget",
            client_phone="+375291112233",
            client_first_name="Никита",
            client_last_name="Иванов",
        )
        first.status = Dialog.Status.CLOSED
        first.closed_at = timezone.now()
        first.save(update_fields=["status", "closed_at", "updated_at"])
        current, current_msg = create_dialog_with_message(
            text="Новый вопрос из Telegram",
            channel="telegram",
            widget_id="",
            placement="telegram",
            client_phone="+375291112233",
            client_first_name="Никита",
            client_last_name="Иванов",
            client_external_id="4242",
        )

        client_view = self.client.get(
            reverse("online_chat_dialog", args=[str(current.id)])
        )
        self.assertEqual(client_view.status_code, 200)
        client_messages = client_view.json()["dialog"]["messages"]
        client_texts = [item["text"] for item in client_messages]
        self.assertIn("Новый вопрос из Telegram", client_texts)
        self.assertNotIn("Старый вопрос из виджета", client_texts)
        self.assertFalse(any(item.get("is_history") for item in client_messages))

        operator_view = self.client.get(
            reverse("online_chat_dialog", args=[str(current.id)]),
            {"include_history": "1"},
        )
        self.assertEqual(operator_view.status_code, 200)
        operator_messages = operator_view.json()["dialog"]["messages"]
        operator_texts = [item["text"] for item in operator_messages]
        self.assertIn("Старый вопрос из виджета", operator_texts)
        self.assertIn("Новый вопрос из Telegram", operator_texts)
        self.assertGreater(operator_view.json()["dialog"]["history_message_count"], 0)
        history_ids = {
            item["id"] for item in operator_messages if item.get("is_history")
        }
        self.assertIn(str(first_msg.id), history_ids)
        self.assertNotIn(str(current_msg.id), history_ids)

    def test_history_does_not_merge_different_phones(self) -> None:
        first, first_msg = create_dialog_with_message(
            text="Вопрос клиента А",
            widget_id="public-widget",
            channel="widget",
            client_phone="+375291112233",
            client_first_name="Никита",
            client_last_name="Иванов",
        )
        first.status = Dialog.Status.CLOSED
        first.closed_at = timezone.now()
        first.save(update_fields=["status", "closed_at", "updated_at"])
        current, _current_msg = create_dialog_with_message(
            text="Вопрос клиента Б",
            widget_id="public-widget",
            channel="widget",
            client_phone="+375299998877",
            client_first_name="Никита",
            client_last_name="Иванов",
        )
        operator_view = self.client.get(
            reverse("online_chat_dialog", args=[str(current.id)]),
            {"include_history": "1"},
        )
        texts = [item["text"] for item in operator_view.json()["dialog"]["messages"]]
        self.assertIn("Вопрос клиента Б", texts)
        self.assertNotIn("Вопрос клиента А", texts)
        self.assertNotIn(str(first_msg.id), {
            item["id"] for item in operator_view.json()["dialog"]["messages"]
        })

    def test_same_phone_links_history_even_if_name_differs(self) -> None:
        first, first_msg = create_dialog_with_message(
            text="Старый вопрос",
            widget_id="public-widget",
            channel="widget",
            client_phone="+375291112233",
            client_first_name="Анна",
            client_last_name="Петрова",
        )
        first.status = Dialog.Status.CLOSED
        first.closed_at = timezone.now()
        first.save(update_fields=["status", "closed_at", "updated_at"])
        current, _current_msg = create_dialog_with_message(
            text="Новый вопрос",
            widget_id="public-widget",
            channel="widget",
            client_phone="+375 29 111-22-33",
            client_first_name="Иван",
            client_last_name="Сидоров",
        )
        operator_view = self.client.get(
            reverse("online_chat_dialog", args=[str(current.id)]),
            {"include_history": "1"},
        )
        texts = [item["text"] for item in operator_view.json()["dialog"]["messages"]]
        self.assertIn("Старый вопрос", texts)
        self.assertIn("Новый вопрос", texts)
        self.assertIn(str(first_msg.id), {
            item["id"] for item in operator_view.json()["dialog"]["messages"] if item.get("is_history")
        })


class WorkScheduleTests(TestCase):
    def test_force_offline_parks_dialog(self) -> None:
        dialog, _ = create_dialog_with_message(
            text="Вопрос ночью",
            force_offline=True,
        )
        self.assertEqual(dialog.status, Dialog.Status.WAITING)
        self.assertEqual(dialog.outcome, Dialog.Outcome.OFFLINE)
        self.assertIn("offline_hours", dialog.routing_reason)
        self.assertIsNone(auto_assign_dialog(dialog))

    def test_calendar_closed_on_weekend(self) -> None:
        from datetime import datetime, time as dt_time
        from django.utils import timezone as dj_tz

        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.enabled = True
        schedule.start_time = dt_time(9, 0)
        schedule.end_time = dt_time(18, 0)
        schedule.workdays = [0, 1, 2, 3, 4]
        schedule.manual_override = WorkScheduleSettings.Override.AUTO
        schedule.save()
        sunday = dj_tz.make_aware(datetime(2026, 8, 16, 12, 0))
        self.assertFalse(schedule.is_open(sunday))
        monday_morning = dj_tz.make_aware(datetime(2026, 8, 17, 10, 0))
        self.assertTrue(schedule.is_open(monday_morning))
        monday_evening = dj_tz.make_aware(datetime(2026, 8, 17, 19, 0))
        self.assertFalse(schedule.is_open(monday_evening))

    def test_day_override_makes_weekday_off(self) -> None:
        from datetime import datetime, time as dt_time
        from django.utils import timezone as dj_tz

        from online_chat.models import WorkScheduleSettings

        schedule = WorkScheduleSettings.get_solo()
        schedule.enabled = True
        schedule.start_time = dt_time(9, 0)
        schedule.end_time = dt_time(18, 0)
        schedule.workdays = [0, 1, 2, 3, 4]
        schedule.day_overrides = {
            "2026-08-17": {"is_workday": False},
            "2026-08-16": {
                "is_workday": True,
                "start_time": "10:00",
                "end_time": "14:00",
            },
        }
        schedule.manual_override = WorkScheduleSettings.Override.AUTO
        schedule.save()
        monday = dj_tz.make_aware(datetime(2026, 8, 17, 12, 0))
        self.assertFalse(schedule.is_open(monday))
        sunday_noon = dj_tz.make_aware(datetime(2026, 8, 16, 12, 0))
        self.assertTrue(schedule.is_open(sunday_noon))
        sunday_evening = dj_tz.make_aware(datetime(2026, 8, 16, 15, 0))
        self.assertFalse(schedule.is_open(sunday_evening))


class ShiftTransitionTests(TestCase):
    """End-of-shift close/open: dialogs return to the queue, operators go offline."""

    def setUp(self) -> None:
        self.department = Department.objects.create(code="support", name="Support")
        self.placement = WidgetPlacement.objects.create(
            widget_id="site-main", name="Main", department=self.department
        )
        self.operator = OperatorProfile.objects.create(
            external_id="op-1",
            display_name="Иванов И.И.",
            presence=OperatorProfile.Presence.ONLINE,
            max_active_dialogs=3,
        )
        self.operator.departments.set([self.department])
        self.supervisor = OperatorProfile.objects.create(
            external_id="sup-1",
            display_name="Козлова Е.В.",
            role=OperatorProfile.Role.SUPERVISOR,
            presence=OperatorProfile.Presence.ONLINE,
            max_active_dialogs=99,
        )
        self.supervisor.departments.set([self.department])

    def test_close_working_day_returns_active_dialogs_and_offlines_operators(self) -> None:
        dialog, _ = create_dialog_with_message(
            text="Нужна консультация",
            widget_id="site-main",
            client_external_id="client-1",
        )
        # Only eligible online operator — auto-assigned immediately on create.
        dialog.refresh_from_db()
        self.assertEqual(dialog.status, Dialog.Status.ACTIVE)
        self.assertEqual(dialog.operator_id, self.operator.id)
        original_created_at = dialog.created_at

        from online_chat.routing_services import close_working_day

        result = close_working_day()
        self.assertEqual(result["returned_to_queue"], 1)

        dialog.refresh_from_db()
        self.assertEqual(dialog.status, Dialog.Status.WAITING)
        self.assertIsNone(dialog.operator)
        self.assertEqual(dialog.operator_name, "")
        # Priority (created_at) is preserved so it re-enters the queue where it was.
        self.assertEqual(dialog.created_at, original_created_at)

        self.operator.refresh_from_db()
        self.assertEqual(self.operator.presence, OperatorProfile.Presence.OFFLINE)

    def test_offline_operator_cannot_be_auto_assigned_after_close(self) -> None:
        from online_chat.routing_services import close_working_day, run_assignments

        close_working_day()
        dialog, _ = create_dialog_with_message(
            text="Ночной вопрос",
            widget_id="site-main",
            client_external_id="client-2",
            force_offline=True,
        )
        self.assertEqual(dialog.outcome, Dialog.Outcome.OFFLINE)
        assigned = run_assignments()
        self.assertEqual(assigned, [])
        dialog.refresh_from_db()
        self.assertEqual(dialog.status, Dialog.Status.WAITING)

    def test_open_working_day_flushes_offline_backlog(self) -> None:
        from online_chat.routing_services import close_working_day, open_working_day

        close_working_day()
        dialog, _ = create_dialog_with_message(
            text="Ночной вопрос",
            widget_id="site-main",
            client_external_id="client-3",
            force_offline=True,
        )
        result = open_working_day()
        dialog.refresh_from_db()
        self.operator.refresh_from_db()
        self.assertEqual(dialog.outcome, "")
        self.assertEqual(dialog.status, Dialog.Status.ACTIVE)
        self.assertEqual(result["assigned"], 1)
        self.assertGreaterEqual(result["operators_onlined"], 1)
        self.assertEqual(self.operator.presence, OperatorProfile.Presence.ONLINE)

    def test_sync_schedule_state_is_idempotent_and_transition_driven(self) -> None:
        from online_chat.models import WorkScheduleSettings
        from online_chat.routing_services import sync_schedule_state

        schedule = WorkScheduleSettings.get_solo()
        schedule.manual_override = WorkScheduleSettings.Override.OPEN
        schedule.save(update_fields=["manual_override"])

        # First observation ever — records state, no side effects triggered.
        first = sync_schedule_state(schedule)
        self.assertFalse(first["changed"])
        schedule.refresh_from_db()
        self.assertTrue(schedule.last_open_state)

        # No actual change → still a no-op.
        second = sync_schedule_state(schedule)
        self.assertFalse(second["changed"])

        dialog, _ = create_dialog_with_message(
            text="Вопрос",
            widget_id="site-main",
            client_external_id="client-4",
        )
        # Only eligible online operator — auto-assigned immediately on create.
        dialog.refresh_from_db()
        self.assertEqual(dialog.status, Dialog.Status.ACTIVE)

        schedule.manual_override = WorkScheduleSettings.Override.CLOSED
        schedule.save(update_fields=["manual_override"])
        closed = sync_schedule_state(schedule)
        self.assertTrue(closed["changed"])
        self.assertEqual(closed["returned_to_queue"], 1)
        dialog.refresh_from_db()
        self.assertEqual(dialog.status, Dialog.Status.WAITING)
