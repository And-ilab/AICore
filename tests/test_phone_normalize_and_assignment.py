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

from django.test import TestCase  # noqa: E402
from django.utils import timezone  # noqa: E402

from online_chat.models import (  # noqa: E402
    AssignmentSettings,
    Department,
    Dialog,
    OperatorProfile,
    format_phone_e164,
    normalize_phone,
)
from online_chat.routing_services import (  # noqa: E402
    operator_has_capacity,
    start_post_close_grace,
    waiting_queue_queryset,
)
from online_chat.services import create_dialog_with_message  # noqa: E402


class PhoneNormalizeTest(TestCase):
    def test_belarus_variants(self):
        self.assertEqual(normalize_phone("80291234567"), "375291234567")
        self.assertEqual(normalize_phone("+375 29 123-45-67"), "375291234567")
        self.assertEqual(normalize_phone("291234567"), "375291234567")
        self.assertEqual(format_phone_e164("80291234567"), "+375291234567")

    def test_foreign_number(self):
        self.assertEqual(normalize_phone("+49 170 1234567"), "491701234567")
        self.assertEqual(format_phone_e164("+49 170 1234567"), "+491701234567")


class AssignmentQueueTest(TestCase):
    def setUp(self):
        self.department = Department.objects.create(
            code="q-test", name="Q", priority=1, max_queue_size=100
        )
        self.operator = OperatorProfile.objects.create(
            external_id="op-q-1",
            display_name="Оператор Очереди",
            role=OperatorProfile.Role.OPERATOR,
            presence=OperatorProfile.Presence.ONLINE,
            auto_assign=True,
            max_active_dialogs=3,
        )
        self.operator.departments.add(self.department)
        self.supervisor = OperatorProfile.objects.create(
            external_id="sv-q-1",
            display_name="Супервизор Очереди",
            role=OperatorProfile.Role.SUPERVISOR,
            presence=OperatorProfile.Presence.ONLINE,
            auto_assign=False,
            max_active_dialogs=3,
        )

    def test_fifo_by_last_client_message(self):
        # Keep dialogs in WAITING — create_dialog_with_message auto-assigns
        # when an eligible online operator exists.
        self.operator.auto_assign = False
        self.operator.save(update_fields=["auto_assign", "updated_at"])
        first, _ = create_dialog_with_message(
            text="первый",
            channel="widget",
            client_phone="+375291111111",
            client_external_id="c1",
        )
        second, _ = create_dialog_with_message(
            text="второй",
            channel="telegram",
            client_phone="+375292222222",
            client_external_id="c2",
        )
        self.assertEqual(first.status, Dialog.Status.WAITING)
        self.assertEqual(second.status, Dialog.Status.WAITING)
        # Newer client activity on the first dialog → it must go to the end.
        first.last_client_message_at = timezone.now() + timedelta(seconds=30)
        first.save(update_fields=["last_client_message_at", "updated_at"])
        ordered = list(waiting_queue_queryset())
        self.assertEqual(len(ordered), 2)
        self.assertEqual(ordered[0].id, second.id)
        self.assertEqual(ordered[-1].id, first.id)

    def test_supervisor_has_no_capacity_limit(self):
        for index in range(5):
            Dialog.objects.create(
                channel="widget",
                status=Dialog.Status.ACTIVE,
                operator=self.supervisor,
                operator_name=self.supervisor.display_name,
                client_first_name="Клиент",
                client_last_name=str(index),
                preview="x",
            )
        self.assertTrue(operator_has_capacity(self.supervisor))
        for index in range(3):
            Dialog.objects.create(
                channel="widget",
                status=Dialog.Status.ACTIVE,
                operator=self.operator,
                operator_name=self.operator.display_name,
                client_first_name="КлиентОп",
                client_last_name=str(index),
                preview="y",
            )
        self.assertFalse(operator_has_capacity(self.operator))

    def test_manual_plus_auto_grace(self):
        settings = AssignmentSettings.get_solo()
        settings.mode = AssignmentSettings.Mode.MANUAL_PLUS_AUTO
        settings.save(update_fields=["mode", "updated_at"])
        # Grace only when closing freed a slot that was at capacity.
        # Post-close: capacity-1 active → before close they were full.
        capacity = self.operator.max_active_dialogs
        for index in range(max(0, capacity - 1)):
            Dialog.objects.create(
                channel="widget",
                status=Dialog.Status.ACTIVE,
                operator=self.operator,
                operator_name=self.operator.display_name,
                client_first_name="Клиент",
                client_last_name=str(index),
                preview="grace",
            )
        before = timezone.now()
        with patch(
            "online_chat.tasks.run_assignments_after_delay.apply_async",
            return_value=None,
        ):
            hold = start_post_close_grace(self.operator)
        self.assertIsNotNone(hold)
        self.assertGreaterEqual(
            hold.until,
            before + timedelta(seconds=AssignmentSettings.GRACE_SECONDS - 1),
        )
        self.assertGreater(hold.until, before)

    def test_manual_plus_auto_grace_skipped_when_under_capacity(self):
        settings = AssignmentSettings.get_solo()
        settings.mode = AssignmentSettings.Mode.MANUAL_PLUS_AUTO
        settings.save(update_fields=["mode", "updated_at"])
        # Operator underloaded (0 active, max 3) → no hold after close.
        with patch(
            "online_chat.tasks.run_assignments_after_delay.apply_async",
            return_value=None,
        ):
            hold = start_post_close_grace(self.operator)
        self.assertIsNone(hold)
