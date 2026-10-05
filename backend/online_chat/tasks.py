from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from online_chat.channel_delivery import deliver_message
from online_chat.models import BaseMessage, Dialog, DialogMessage, WidgetPlacement
from online_chat.routing_services import record_event


@shared_task(
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 4},
)
def deliver_channel_message(message_id: str) -> dict[str, str | bool]:
    message = DialogMessage.objects.select_related("dialog").get(pk=message_id)
    try:
        result = deliver_message(message)
    except Exception as exc:  # noqa: BLE001 — persist provider failure for ops
        message.channel_delivery_status = DialogMessage.ChannelDeliveryStatus.FAILED
        message.channel_delivery_error = str(exc)[:1000]
        message.save(
            update_fields=["channel_delivery_status", "channel_delivery_error"]
        )
        raise

    message.channel_delivery_status = (
        DialogMessage.ChannelDeliveryStatus.SENT
        if result.sent
        else DialogMessage.ChannelDeliveryStatus.FAILED
    )
    message.channel_delivery_error = "" if result.sent else result.detail
    if result.external_message_id:
        message.external_message_id = result.external_message_id
    message.save(
        update_fields=[
            "channel_delivery_status",
            "channel_delivery_error",
            "external_message_id",
        ]
    )
    return {
        "sent": result.sent,
        "external_message_id": result.external_message_id,
        "detail": result.detail,
    }


@shared_task(
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_delayed_base_message(dialog_id: str, base_message_id: str) -> dict[str, str | bool]:
    """Send one base message after its configured delay, if still applicable."""
    from online_chat.routing_services import line_is_open
    from online_chat.services import (
        HOLD_SEND_PHASES,
        _base_message_already_sent,
        _base_message_matches,
        _create_bot_message,
    )

    dialog = Dialog.objects.filter(pk=dialog_id).first()
    if dialog is None:
        return {"sent": False, "reason": "dialog_not_found"}
    message = BaseMessage.objects.filter(pk=base_message_id, is_active=True).first()
    if message is None:
        return {"sent": False, "reason": "base_message_not_found"}
    is_hold = message.send_phase in HOLD_SEND_PHASES
    is_offline = (
        message.send_phase == BaseMessage.SendPhase.OFFLINE
        or message.message_type == BaseMessage.MessageType.OFFLINE
    )
    if is_hold and (
        dialog.status != Dialog.Status.WAITING or dialog.bot_active
    ):
        return {"sent": False, "reason": "dialog_not_waiting"}
    if is_offline and line_is_open() and dialog.outcome != Dialog.Outcome.OFFLINE:
        return {"sent": False, "reason": "line_open"}
    placement_config = None
    if dialog.channel == "widget":
        placement_config = WidgetPlacement.objects.filter(widget_id=dialog.widget_id).first()
    if not _base_message_matches(message, dialog, placement_config):
        return {"sent": False, "reason": "target_mismatch"}
    if _base_message_already_sent(dialog, message):
        return {"sent": False, "reason": "already_sent"}
    _create_bot_message(dialog, message.text, base_message=message)
    return {"sent": True, "reason": "ok"}


@shared_task(
    autoretry_for=(OSError, TimeoutError),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_hold_base_message(dialog_id: str, base_message_id: str) -> dict[str, str | bool]:
    """Hold-phase alias kept for existing callers and tests."""
    return send_delayed_base_message(dialog_id, base_message_id)


@shared_task
def run_assignments_after_delay(operator_id: str = "") -> dict[str, int]:
    """Resume auto-assign after post-close grace (manual+auto mode)."""
    from online_chat.models import OperatorProfile
    from online_chat.routing_services import clear_assignment_hold, run_assignments

    if operator_id:
        operator = OperatorProfile.objects.filter(pk=operator_id).first()
        if operator:
            clear_assignment_hold(operator)
            assigned = []
            for department in operator.departments.filter(is_active=True):
                assigned.extend(run_assignments(department=department))
            if not assigned and not operator.departments.exists():
                assigned = run_assignments()
            return {"assigned": len(assigned)}
    assigned = run_assignments()
    return {"assigned": len(assigned)}


@shared_task
def sync_work_schedule() -> dict[str, object]:
    """Periodic check that drives the automatic online/offline transition.

    Production has no manual button: the admin configures the work schedule
    once (``WorkScheduleSettings``), and this task notices when the clock
    crosses the open/close boundary and applies the matching side effects
    (return active dialogs to the shared queue + take operators offline, or
    flush the offline backlog) — see ``routing_services.sync_schedule_state``.
    Idempotent: a no-op whenever the resolved state hasn't actually changed.
    """
    from online_chat.routing_services import sync_schedule_state

    result = sync_schedule_state()
    if result.get("changed"):
        from online_chat.services import ARM_GROUP, broadcast
        from online_chat.models import WorkScheduleSettings

        obj = WorkScheduleSettings.get_solo()
        broadcast(ARM_GROUP, "work_schedule.updated", {
            "is_open": obj.is_open(),
            "manual_override": obj.manual_override,
        })
    return result


@shared_task
def classify_stale_dialogs() -> dict[str, int]:
    timeout = max(60, int(settings.ONLINE_CHAT_LOST_TIMEOUT_SECONDS))
    cutoff = timezone.now() - timedelta(seconds=timeout)
    stale = Dialog.objects.filter(
        client_online=False,
        status__in=(Dialog.Status.WAITING, Dialog.Status.ACTIVE),
        client_last_seen_at__lt=cutoff,
        outcome=Dialog.Outcome.OFFLINE,
    )
    count = 0
    for dialog in stale.iterator():
        dialog.outcome = Dialog.Outcome.LOST
        dialog.save(update_fields=["outcome", "updated_at"])
        record_event(
            dialog,
            "classified_lost",
            actor_name="system",
            payload={"timeout_seconds": timeout},
        )
        count += 1
    return {"classified_lost": count}
