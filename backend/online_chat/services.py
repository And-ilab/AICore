from __future__ import annotations

import logging
import re
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from django.utils import timezone

from audit.events import (
    CATEGORY_DATA_SECURITY,
    ONLINE_CHAT_CLIENT_BLOCKED,
    ONLINE_CHAT_CLIENT_UNBLOCKED,
    RESULT_SUCCESS,
)
from audit.schema import AuditSubject
from audit.service import emit
from online_chat.mail import send_dialog_transcript
from online_chat.models import (
    AssignmentSettings,
    BaseMessage,
    BotConfiguration,
    ClientBlock,
    Dialog,
    DialogCloseTopicNode,
    DialogFeedback,
    DialogMessage,
    DialogTranscriptEmail,
    OperatorProfile,
    WidgetPlacement,
    format_phone_e164,
    normalize_phone,
)
from online_chat.routing_services import (
    accept_waiting_dialog,
    auto_assign_dialog,
    department_queue_is_full,
    line_is_open,
    record_event,
    select_department,
    start_post_close_grace,
    transfer_to_operator,
)

logger = logging.getLogger(__name__)

ARM_GROUP = "online_chat_arm"

HOLD_SEND_PHASES = (
    BaseMessage.SendPhase.HOLD,
    BaseMessage.SendPhase.MID_DIALOG,
)
_WAIT_CYCLE_EVENTS = ("created", "returned_to_queue", "line_closed", "line_opened")


def _active_bot_for_department(department_id: object | None) -> BotConfiguration | None:
    if department_id:
        department_bot = (
            BotConfiguration.objects.filter(department_id=department_id, is_active=True)
            .order_by("created_at")
            .first()
        )
        if department_bot:
            return department_bot
    return (
        BotConfiguration.objects.filter(department__isnull=True, is_active=True)
        .order_by("created_at")
        .first()
    )


def _active_bot(dialog: Dialog) -> BotConfiguration | None:
    return _active_bot_for_department(dialog.department_id)


def _create_bot_message(
    dialog: Dialog,
    text: str,
    *,
    base_message: BaseMessage | None = None,
) -> DialogMessage:
    delivery_status = DialogMessage.ChannelDeliveryStatus.NOT_REQUIRED
    if dialog.channel != "widget":
        delivery_status = DialogMessage.ChannelDeliveryStatus.PENDING
    message = DialogMessage.objects.create(
        dialog=dialog,
        speaker=DialogMessage.Speaker.BOT,
        text=text,
        receipt_status=DialogMessage.ReceiptStatus.DELIVERED,
        channel_delivery_status=delivery_status,
        source_base_message_id=base_message.id if base_message is not None else None,
    )
    payload = serialize_message(message)
    broadcast(dialog_group(str(dialog.id)), "message.created", payload)
    broadcast(ARM_GROUP, "message.created", payload)
    if delivery_status == DialogMessage.ChannelDeliveryStatus.PENDING:
        from online_chat.tasks import deliver_channel_message

        try:
            deliver_channel_message.delay(str(message.id))
        except Exception:  # noqa: BLE001 — broker down: deliver inline
            deliver_channel_message(str(message.id))
    return message


def _base_message_matches(
    message: BaseMessage,
    dialog: Dialog,
    placement_config: WidgetPlacement | None = None,
) -> bool:
    targets = [str(value).strip() for value in (message.channels or []) if str(value).strip()]
    if not targets:
        if message.placement_id:
            targets = [f"widget:{message.placement_id}"]
        elif message.channel:
            targets = [message.channel.strip()]
        else:
            return True

    if dialog.channel in targets:
        return True
    if dialog.channel == "widget" and "widget" in targets:
        return True
    if dialog.channel != "widget":
        return False
    placement_config = placement_config or WidgetPlacement.objects.filter(
        widget_id=dialog.widget_id
    ).first()
    if placement_config is None:
        return False
    placement_id = str(placement_config.id)
    widget_id = placement_config.widget_id
    return (
        f"widget:{placement_id}" in targets
        or f"widget:{widget_id}" in targets
        or placement_id in targets
        or widget_id in targets
    )


def _wait_cycle_started_at(dialog: Dialog):
    event = (
        dialog.events.filter(type__in=_WAIT_CYCLE_EVENTS)
        .order_by("-created_at")
        .first()
    )
    if event is None or event.type == "created":
        return dialog.created_at
    return event.created_at


def _base_message_already_sent(dialog: Dialog, message: BaseMessage) -> bool:
    since = _wait_cycle_started_at(dialog)
    qs = DialogMessage.objects.filter(
        dialog=dialog,
        speaker=DialogMessage.Speaker.BOT,
        created_at__gte=since,
    )
    if message.id:
        if qs.filter(source_base_message_id=message.id).exists():
            return True
    return qs.filter(text=message.text).exists()


def _iter_offline_base_messages():
    return BaseMessage.objects.filter(
        is_active=True,
    ).filter(
        Q(message_type=BaseMessage.MessageType.OFFLINE)
        | Q(send_phase=BaseMessage.SendPhase.OFFLINE)
    ).order_by("sort_order", "created_at")


def _hold_delay_offset(
    dialog: Dialog,
    placement_config: WidgetPlacement | None = None,
) -> int:
    """Keep hold after offline notices when the line is closed."""
    if dialog.outcome != Dialog.Outcome.OFFLINE:
        return 0
    delays = [
        max(0, int(message.delay_seconds or 0))
        for message in _iter_offline_base_messages()
        if _base_message_matches(message, dialog, placement_config)
    ]
    return max(delays) if delays else 0


def _schedule_base_message(
    dialog: Dialog,
    message: BaseMessage,
    *,
    extra_delay: int = 0,
    placement_config: WidgetPlacement | None = None,
    task=None,
) -> bool:
    """Send now (delay 0) or enqueue Celery countdown. Returns True if queued/sent."""
    if not _base_message_matches(message, dialog, placement_config):
        return False
    if _base_message_already_sent(dialog, message):
        return False
    delay = max(0, int(message.delay_seconds or 0)) + max(0, int(extra_delay))
    from online_chat.tasks import send_delayed_base_message

    worker = task or send_delayed_base_message
    kwargs = {
        "dialog_id": str(dialog.id),
        "base_message_id": str(message.id),
    }
    if delay == 0:
        worker(**kwargs)
    else:
        try:
            worker.apply_async(kwargs=kwargs, countdown=delay)
        except Exception:  # noqa: BLE001 — broker down: run inline
            worker(**kwargs)
    return True


def _send_base_messages(
    dialog: Dialog,
    phase: str,
    placement_config: WidgetPlacement | None = None,
) -> int:
    sent = 0
    messages = BaseMessage.objects.filter(
        is_active=True,
        send_phase=phase,
    ).order_by("sort_order", "created_at")
    for message in messages:
        if _schedule_base_message(
            dialog, message, placement_config=placement_config
        ):
            sent += 1
    return sent


def _enqueue_hold_base_messages(
    dialog: Dialog,
    placement_config: WidgetPlacement | None = None,
) -> int:
    """Schedule delayed base messages for the waiting-for-operator phase."""
    if dialog.status != Dialog.Status.WAITING or dialog.bot_active:
        return 0
    from online_chat.tasks import send_hold_base_message

    extra = _hold_delay_offset(dialog, placement_config)
    queued = 0
    messages = BaseMessage.objects.filter(
        is_active=True,
        send_phase__in=HOLD_SEND_PHASES,
    ).order_by("sort_order", "created_at")
    for message in messages:
        if _schedule_base_message(
            dialog,
            message,
            extra_delay=extra,
            placement_config=placement_config,
            task=send_hold_base_message,
        ):
            queued += 1
    return queued


def enqueue_hold_for_waiting_dialogs() -> int:
    """Re-arm hold messages for live waiting dialogs (line just opened)."""
    queued = 0
    waiting = Dialog.objects.filter(
        status=Dialog.Status.WAITING,
        bot_active=False,
    ).exclude(outcome=Dialog.Outcome.OFFLINE)
    for dialog in waiting:
        record_event(dialog, "line_opened", actor_name="system")
        queued += _enqueue_hold_base_messages(dialog)
    return queued


def park_waiting_dialogs_offline() -> dict[str, int]:
    """Mark waiting dialogs as offline intake and send вне графика notices."""
    parked = 0
    notices = 0
    holds = 0
    waiting = Dialog.objects.filter(status=Dialog.Status.WAITING)
    for dialog in waiting:
        update_fields = ["updated_at"]
        if dialog.outcome != Dialog.Outcome.OFFLINE:
            dialog.outcome = Dialog.Outcome.OFFLINE
            update_fields.insert(0, "outcome")
        dialog.save(update_fields=update_fields)
        record_event(dialog, "line_closed", actor_name="system")
        notices += _send_offline_notice(dialog)
        holds += _enqueue_hold_base_messages(dialog)
        parked += 1
    return {"parked": parked, "offline_notices": notices, "holds_queued": holds}


def _send_offline_notice(
    dialog: Dialog,
    placement_config: WidgetPlacement | None = None,
) -> int:
    """Send the admin-configured "вне графика" message(s) from Базовые сообщения.

    If no offline base message is configured, nothing is sent (per product spec).
    """
    sent = 0
    for message in _iter_offline_base_messages():
        if _schedule_base_message(
            dialog, message, placement_config=placement_config
        ):
            sent += 1
    return sent


def _handle_bot_turn(dialog: Dialog, client_text: str) -> None:
    bot = _active_bot(dialog)
    if not bot or not dialog.bot_active:
        return
    normalized = client_text.casefold()
    response = ""
    if isinstance(bot.trigger_responses, dict):
        for trigger, candidate in bot.trigger_responses.items():
            if str(trigger).casefold() in normalized:
                response = str(candidate)
                break
    dialog.bot_turns += 1
    should_handoff = not response or dialog.bot_turns >= bot.max_bot_turns
    if should_handoff:
        dialog.bot_active = False
        dialog.routing_reason = f"bot_handoff:{bot.name}"
        dialog.save(
            update_fields=[
                "bot_active",
                "bot_turns",
                "routing_reason",
                "updated_at",
            ]
        )
        _send_base_messages(dialog, BaseMessage.SendPhase.AFTER_BOT)
        _create_bot_message(
            dialog,
            bot.handoff_message or bot.fallback_message,
        )
        auto_assign_dialog(dialog)
        record_event(dialog, "bot_handoff", actor_name=bot.name)
        return
    dialog.save(update_fields=["bot_turns", "updated_at"])
    _create_bot_message(dialog, response)
    record_event(
        dialog,
        "bot_replied",
        actor_name=bot.name,
        payload={"turn": dialog.bot_turns},
    )


def dialog_group(dialog_id: str) -> str:
    return f"online_chat_dialog_{dialog_id}"


def _operator_photo_api_path(operator_id: object) -> str:
    oid = str(operator_id or "").strip()
    if not oid:
        return ""
    return f"/api/v1/online-chat/operators/{oid}/photo/"


def _sanitize_operator_avatar(operator_id: str, raw_avatar: str) -> str:
    """Never put data: URLs on the wire; prefer the stable photo endpoint."""
    oid = (operator_id or "").strip()
    photo = (raw_avatar or "").strip()
    if oid and photo:
        return _operator_photo_api_path(oid)
    if photo.startswith("http://") or photo.startswith("https://"):
        return photo
    if photo.startswith("/api/") and "/photo/" in photo:
        return photo
    return ""


def _operator_profile_by_name(display_name: str) -> OperatorProfile | None:
    name = (display_name or "").strip()
    if not name:
        return None
    return (
        OperatorProfile.objects.filter(display_name=name)
        .order_by("-is_active")
        .first()
    )


def _operator_photo_url(
    *,
    operator: OperatorProfile | None = None,
    display_name: str = "",
) -> str:
    if operator is not None:
        return getattr(operator, "photo_url", "") or ""
    profile = _operator_profile_by_name(display_name)
    if profile is None:
        return ""
    return getattr(profile, "photo_url", "") or ""


def _operator_avatar(dialog: Dialog) -> str:
    """Photo of the bank employee handling the dialog, for the client widget."""
    if dialog.operator_id:
        try:
            url = _operator_photo_url(operator=dialog.operator)
            if url:
                return _operator_photo_api_path(dialog.operator_id)
        except Exception:  # pragma: no cover - defensive for missing relation
            pass
    if dialog.operator_name:
        profile = _operator_profile_by_name(dialog.operator_name)
        if profile is not None and (profile.photo_url or "").strip():
            return _operator_photo_api_path(profile.id)
    return ""


def _operator_assignment_timeline(dialog: Dialog) -> list[tuple[object, str]]:
    """Chronological operator handoffs for per-message avatar attribution."""
    rows: list[tuple[object, str]] = []
    for event in dialog.events.filter(type__in=("accepted", "transferred")).order_by(
        "created_at"
    ):
        if event.type == "accepted":
            name = (event.actor_name or "").strip()
        else:
            name = str((event.payload or {}).get("to") or "").strip()
        if name:
            rows.append((event.created_at, name))
    return rows


def _operator_name_at(
    timeline: list[tuple[object, str]],
    at,
    *,
    fallback: str = "",
) -> str:
    name = ""
    for ts, operator_name in timeline:
        if ts <= at:
            name = operator_name
        else:
            break
    return name or fallback


def _operator_profile_cache(names: set[str]) -> dict[str, OperatorProfile]:
    cleaned = {item.strip() for item in names if item and item.strip()}
    if not cleaned:
        return {}
    return {
        profile.display_name: profile
        for profile in OperatorProfile.objects.filter(display_name__in=cleaned).order_by(
            "is_active"
        )
    }


def serialize_message(
    message: DialogMessage,
    *,
    operator_name: str = "",
    operator_avatar: str = "",
    operator_id: str = "",
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(message.id),
        "dialog_id": str(message.dialog_id),
        "speaker": message.speaker,
        "text": message.display_text(),
        "raw_text": "" if message.is_deleted else message.text,
        "receipt_status": message.receipt_status,
        "reply_to_id": str(message.reply_to_id) if message.reply_to_id else None,
        "quoted_text": message.quoted_text,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "is_deleted": message.is_deleted,
        "attachment_name": message.attachment_name,
        "attachment_key": message.attachment_key,
        "attachment_content_type": message.attachment_content_type,
        "attachment_size": message.attachment_size,
        "attachment_scan_status": message.attachment_scan_status,
        "external_message_id": message.external_message_id,
        "channel_delivery_status": message.channel_delivery_status,
        "channel_delivery_error": message.channel_delivery_error,
        "response_origin": message.response_origin,
        "created_at": message.created_at.isoformat(),
    }
    if message.speaker == DialogMessage.Speaker.OPERATOR:
        name = operator_name.strip()
        if name:
            payload["operator_name"] = name
        profile_id = str(operator_id).strip()
        avatar = operator_avatar.strip()
        profile = None
        if not profile_id and name:
            profile = _operator_profile_by_name(name)
            if profile:
                profile_id = str(profile.id)
        if not avatar and profile is not None:
            avatar = profile.photo_url or ""
        if not avatar and name and profile is None:
            avatar = _operator_photo_url(display_name=name)
        if profile_id:
            payload["operator_id"] = profile_id
        public_avatar = _sanitize_operator_avatar(profile_id, avatar)
        if public_avatar:
            payload["operator_avatar"] = public_avatar
    return payload


def serialize_messages_for_dialog(
    dialog: Dialog,
    messages,
    *,
    timeline: list[tuple[object, str]] | None = None,
    photo_cache: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows = list(messages)
    if not rows:
        return []
    del photo_cache  # legacy arg — profiles resolved internally
    assignment_timeline = timeline if timeline is not None else _operator_assignment_timeline(
        dialog
    )
    names = {dialog.operator_name} if dialog.operator_name else set()
    names.update(name for _, name in assignment_timeline)
    profile_cache = _operator_profile_cache(names)
    current_operator = None
    if dialog.operator_id:
        try:
            current_operator = dialog.operator
        except Exception:  # pragma: no cover - missing relation
            current_operator = None
    serialized: list[dict[str, Any]] = []
    for message in rows:
        if message.speaker == DialogMessage.Speaker.OPERATOR:
            name = _operator_name_at(
                assignment_timeline,
                message.created_at,
                fallback=dialog.operator_name,
            )
            profile = profile_cache.get(name)
            if profile is None and current_operator is not None:
                profile = current_operator
            serialized.append(
                serialize_message(
                    message,
                    operator_name=name,
                    operator_avatar=(profile.photo_url or "") if profile else "",
                    operator_id=str(profile.id) if profile else "",
                )
            )
        else:
            serialized.append(serialize_message(message))
    return serialized


def serialize_feedback(feedback: DialogFeedback) -> dict[str, Any]:
    return {
        "id": str(feedback.id),
        "dialog_id": str(feedback.dialog_id),
        "rating": feedback.rating,
        "comment": feedback.comment,
        "created_at": feedback.created_at.isoformat(),
    }


def serialize_transcript_email(record: DialogTranscriptEmail) -> dict[str, Any]:
    return {
        "id": str(record.id),
        "dialog_id": str(record.dialog_id),
        "email": record.email,
        "status": record.status,
        "error_detail": record.error_detail,
        "created_at": record.created_at.isoformat(),
        "sent_at": record.sent_at.isoformat() if record.sent_at else None,
    }


def serialize_client_block(block: ClientBlock) -> dict[str, Any]:
    return {
        "id": str(block.id),
        "phone": block.phone,
        "phone_normalized": block.phone_normalized,
        "reason": block.reason,
        "blocked_by": block.blocked_by,
        "dialog_id": str(block.dialog_id) if block.dialog_id else None,
        "is_active": block.is_active,
        "created_at": block.created_at.isoformat(),
        "lifted_at": block.lifted_at.isoformat() if block.lifted_at else None,
    }


def _last_human_message(dialog: Dialog) -> DialogMessage | None:
    return (
        dialog.messages.filter(
            is_deleted=False,
            speaker__in=(
                DialogMessage.Speaker.CLIENT,
                DialogMessage.Speaker.OPERATOR,
            ),
        )
        .order_by("-created_at")
        .first()
    )


def dialog_needs_reply(dialog: Dialog) -> bool:
    """True when the last human message is from the client (operator must answer)."""
    if dialog.status in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
        return False
    last = _last_human_message(dialog)
    return last is not None and last.speaker == DialogMessage.Speaker.CLIENT


def _wait_anchor(dialog: Dialog):
    """Absolute timestamp for the SLA stopwatch (None when not waiting)."""
    if dialog.status in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
        return None
    if not dialog_needs_reply(dialog):
        return None
    last_client = (
        dialog.messages.filter(
            speaker=DialogMessage.Speaker.CLIENT,
            is_deleted=False,
        )
        .order_by("-created_at")
        .first()
    )
    if last_client is None:
        return None
    anchor = last_client.created_at
    if dialog.accepted_at and last_client.created_at <= dialog.accepted_at:
        anchor = dialog.accepted_at
    return anchor


def _wait_seconds(dialog: Dialog) -> int:
    """SLA wait while a client message awaits operator reply; 0 after operator answers.

    TZ: timer from last unanswered client message; resets when operator works/replies.
    Unassigned queue: from client message time. After accept of that same message:
    anchor moves to accepted_at (SLA reset on take). New client messages after accept
    restart the timer from their created_at.
    """
    anchor = _wait_anchor(dialog)
    if anchor is None:
        return 0
    return max(0, int((timezone.now() - anchor).total_seconds()))


def is_test_client_dialog(dialog: Dialog) -> bool:
    """Simulator / seed clients — sufler must stay disabled for these."""
    external = (dialog.client_external_id or "").strip().casefold()
    if external.startswith("sim-") or external.startswith("dev-sim"):
        return True
    first = (dialog.client_first_name or "").strip().casefold()
    last = (dialog.client_last_name or "").strip()
    if first == "клиент" and last.isdigit():
        return True
    preview = (dialog.preview or "").casefold()
    if preview.startswith("тестовое обращение клиента"):
        return True
    return False


_CHANNEL_LABELS = {
    "widget": "Виджет сайта",
    "telegram": "Telegram",
    "viber": "Viber",
    "vk": "VK",
    "ok": "OK",
    "api": "API",
    "email": "E-mail",
}


def channel_label(channel: str) -> str:
    key = (channel or "").strip().lower()
    return _CHANNEL_LABELS.get(key, channel or "неизвестный канал")


def phones_linked(left: str, right: str) -> bool:
    """Strict client identity: same phone number only.

    Two phones are the same subscriber when their normalized forms are equal, or
    when one is the national form of the other (same last 9 digits — с/без кода
    страны). No fuzzy typo/last-7 matching: different numbers = different clients.
    """
    a = normalize_phone(left)
    b = normalize_phone(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 9 and len(b) >= 9 and a[-9:] == b[-9:]


def _name_token_set(first_name: str, last_name: str) -> frozenset[str]:
    parts = []
    for raw in (first_name or "", last_name or ""):
        for token in re.split(r"[\s\-]+", raw.strip().casefold()):
            if len(token) >= 2:
                parts.append(token)
    return frozenset(parts)


def names_linked(
    first_a: str,
    last_a: str,
    first_b: str,
    last_b: str,
) -> bool:
    """Same person even if widget/TG swapped имя/фамилия fields."""
    left = _name_token_set(first_a, last_a)
    right = _name_token_set(first_b, last_b)
    return len(left) >= 2 and left == right


def history_identity_query(
    *,
    phone: str = "",
    external_id: str = "",
    first_name: str = "",
    last_name: str = "",
) -> Q:
    """Match dialogs by phone number (strict) or exact same-channel external id.

    Client identity is the phone number: same phone → same client, different
    phone → different clients, regardless of matching name/company. FIO is never
    used for matching (it caused messages to leak between different clients).
    The external id (e.g. Telegram chat_id) still links the same user on the
    same channel when a phone is not available.
    """
    # first_name / last_name intentionally ignored — kept for call-site compat.
    _ = (first_name, last_name)
    normalized = normalize_phone(phone)
    ext = (external_id or "").strip()

    matched_ids: list[Any] = []
    if normalized:
        matched_ids = [
            item.id
            for item in Dialog.objects.only("id", "client_phone").iterator(
                chunk_size=500
            )
            if phones_linked(item.client_phone, normalized)
        ]

    if not matched_ids and not ext:
        return Q()

    query = Q()
    if matched_ids:
        query |= Q(id__in=matched_ids)
    if ext:
        query |= Q(client_external_id=ext)
    return query if query else Q(pk__in=[])


def _clean_client_fields(raw: object) -> list[dict[str, str]]:
    """Normalize pre-chat form data to a display list of {label, value}."""
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if label and value:
            cleaned.append({"label": label[:120], "value": value[:500]})
    return cleaned


def serialize_dialog(
    dialog: Dialog,
    *,
    include_messages: bool = False,
    include_history: bool = False,
) -> dict[str, Any]:
    needs_reply = dialog_needs_reply(dialog)
    wait_anchor = _wait_anchor(dialog)
    feedback = DialogFeedback.objects.filter(dialog_id=dialog.id).only("rating").first()
    payload: dict[str, Any] = {
        "id": str(dialog.id),
        "ref_code": dialog.ref_code(),
        "widget_id": dialog.widget_id,
        "placement": dialog.placement,
        "channel": dialog.channel,
        "status": dialog.status,
        "initiated_by": dialog.initiated_by,
        "client_first_name": dialog.client_first_name,
        "client_last_name": dialog.client_last_name,
        "client_phone": dialog.client_phone,
        "client_external_id": dialog.client_external_id,
        "client_fields": _clean_client_fields(dialog.client_fields),
        "client_ip": dialog.client_ip,
        "entry_url": dialog.entry_url,
        "locale": dialog.locale,
        "client_name": dialog.client_display_name(),
        "client_online": dialog.client_online,
        "operator_name": dialog.operator_name,
        "operator_id": str(dialog.operator_id) if dialog.operator_id else None,
        "operator_avatar": _operator_avatar(dialog),
        "department_id": str(dialog.department_id) if dialog.department_id else None,
        "department_name": dialog.department.name if dialog.department_id else None,
        "routing_reason": dialog.routing_reason,
        "outcome": dialog.outcome,
        "preview": dialog.preview,
        "close_topic": dialog.close_topic,
        "close_topic_id": str(dialog.close_topic_node_id) if dialog.close_topic_node_id else None,
        "created_at": dialog.created_at.isoformat(),
        "updated_at": dialog.updated_at.isoformat(),
        "accepted_at": dialog.accepted_at.isoformat() if dialog.accepted_at else None,
        "closed_at": dialog.closed_at.isoformat() if dialog.closed_at else None,
        "last_client_message_at": (
            dialog.last_client_message_at.isoformat() if dialog.last_client_message_at else None
        ),
        "first_response_at": (
            dialog.first_response_at.isoformat() if dialog.first_response_at else None
        ),
        "sla_deadline_at": dialog.sla_deadline_at.isoformat() if dialog.sla_deadline_at else None,
        "client_last_seen_at": (
            dialog.client_last_seen_at.isoformat() if dialog.client_last_seen_at else None
        ),
        "needs_reply": needs_reply,
        "wait_seconds": (
            max(0, int((timezone.now() - wait_anchor).total_seconds()))
            if wait_anchor is not None
            else 0
        ),
        "wait_anchor_at": wait_anchor.isoformat() if wait_anchor is not None else None,
        "is_test_client": is_test_client_dialog(dialog),
        "has_feedback": feedback is not None,
        "feedback_rating": feedback.rating if feedback is not None else None,
    }
    if include_messages:
        current_messages = serialize_messages_for_dialog(
            dialog,
            dialog.messages.all(),
        )
        history_messages = (
            _prior_dialog_messages_for_operator(dialog) if include_history else []
        )
        payload["messages"] = history_messages + current_messages
        payload["history_message_count"] = len(history_messages)
    return payload


def _history_separator_payload(
    *,
    separator_id: str,
    dialog_id: str,
    text: str,
    created_at,
) -> dict[str, Any]:
    return {
        "id": separator_id,
        "dialog_id": dialog_id,
        "speaker": "system",
        "text": text,
        "raw_text": text,
        "receipt_status": "read",
        "reply_to_id": None,
        "quoted_text": "",
        "edited_at": None,
        "is_deleted": False,
        "attachment_name": "",
        "attachment_key": "",
        "attachment_content_type": "",
        "attachment_size": 0,
        "attachment_scan_status": "not_required",
        "external_message_id": "",
        "channel_delivery_status": "not_required",
        "channel_delivery_error": "",
        "response_origin": "",
        "created_at": created_at.isoformat(),
        "is_history": True,
    }


def _prior_dialog_messages_for_operator(dialog: Dialog) -> list[dict[str, Any]]:
    """Prepend prior appeals of the same client for ARM scrollback.

    Client channels never receive these — only operator getDialog with
    include_history=1. Identity is strict: the phone number (cross-channel) or
    the exact same-channel external id. FIO is never used.
    """
    query = history_identity_query(
        phone=dialog.client_phone,
        external_id=dialog.client_external_id,
        first_name=dialog.client_first_name,
        last_name=dialog.client_last_name,
    )
    if not query:
        return []
    prior = list(
        Dialog.objects.filter(query)
        .exclude(pk=dialog.pk)
        .prefetch_related("messages")
        .order_by("created_at")[:100]
    )
    packed: list[dict[str, Any]] = []
    current_id = str(dialog.id)
    for prior_dialog in prior:
        when = prior_dialog.closed_at or prior_dialog.created_at
        when_label = when.strftime("%d.%m.%Y %H:%M") if when else ""
        topic = (prior_dialog.close_topic or "").strip() or "без темы"
        channel = channel_label(prior_dialog.channel)
        sep_text = f"—— Предыдущее обращение · {channel} · {when_label} · {topic} ——"
        packed.append(
            _history_separator_payload(
                separator_id=f"history-sep-{prior_dialog.id}",
                dialog_id=current_id,
                text=sep_text,
                created_at=when,
            )
        )
        for message in prior_dialog.messages.all():
            item = serialize_message(message)
            item["is_history"] = True
            packed.append(item)
    if packed:
        packed.append(
            _history_separator_payload(
                separator_id=f"history-sep-current-{dialog.id}",
                dialog_id=current_id,
                text="—— Текущее обращение ——",
                created_at=dialog.created_at,
            )
        )
    return packed


def broadcast(group: str, event_type: str, payload: dict[str, Any]) -> None:
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        group,
        {"type": "online_chat.event", "event_type": event_type, "payload": payload},
    )


def is_phone_blocked(phone: str) -> ClientBlock | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    return (
        ClientBlock.objects.filter(phone_normalized=normalized, is_active=True)
        .order_by("-created_at")
        .first()
    )


def _emit_block_audit(*, event_type: str, description: str, details: dict[str, Any]) -> None:
    try:
        emit(
            category=CATEGORY_DATA_SECURITY,
            event_type=event_type,
            result=RESULT_SUCCESS,
            subject=AuditSubject(user_login="online-chat", roles=("operator",)),
            module="online_chat",
            description=description,
            severity="warning",
            details=details,
        )
    except Exception:  # noqa: BLE001 — audit must not break chat
        logger.exception("online_chat audit emit failed")


def create_dialog_with_message(
    *,
    text: str,
    widget_id: str = "site-belarusbank",
    placement: str = "website",
    client_first_name: str = "",
    client_last_name: str = "",
    client_phone: str = "",
    client_external_id: str = "",
    entry_url: str = "",
    locale: str = "ru",
    channel: str = "widget",
    initiated_by: str = Dialog.InitiatedBy.CLIENT,
    operator_name: str = "",
    client_fields: list[dict[str, str]] | None = None,
    client_ip: str = "",
    force_offline: bool = False,
    skip_auto_assign: bool = False,
) -> tuple[Dialog, DialogMessage]:
    if is_phone_blocked(client_phone):
        raise PermissionError("client is blocked")

    preview = text.strip()[:500]
    status = Dialog.Status.WAITING
    if initiated_by == Dialog.InitiatedBy.OPERATOR and operator_name.strip():
        status = Dialog.Status.ACTIVE
    # Client arriving outside working hours is parked until the line opens.
    # ``force_offline`` lets internal callers (tests, tooling) simulate that
    # without depending on the real clock/schedule.
    line_open = line_is_open()
    is_offline_intake = initiated_by == Dialog.InitiatedBy.CLIENT and (
        force_offline or not line_open
    )
    normalized_phone = format_phone_e164(client_phone) if client_phone else ""

    department, placement_config, routing_reason = select_department(
        widget_id=widget_id,
        channel=channel,
        context={"placement": placement},
    )
    queue_full = department_queue_is_full(department)
    if queue_full:
        routing_reason = f"{routing_reason};queue_full"
    if is_offline_intake:
        routing_reason = (
            f"{routing_reason};offline_hours" if routing_reason else "offline_hours"
        )
    bot = _active_bot_for_department(department.id if department else None)
    now = timezone.now()
    dialog = Dialog.objects.create(
        widget_id=widget_id,
        placement=placement,
        channel=channel,
        status=status,
        initiated_by=initiated_by,
        client_first_name=client_first_name.strip(),
        client_last_name=client_last_name.strip(),
        client_phone=normalized_phone or client_phone.strip(),
        client_external_id=client_external_id.strip(),
        client_fields=_clean_client_fields(client_fields),
        client_ip=client_ip.strip()[:64],
        entry_url=entry_url.strip(),
        locale=locale.strip() or "ru",
        operator_name=operator_name.strip(),
        preview=preview,
        department=department,
        routing_reason=routing_reason,
        bot_active=bool(bot) and not queue_full and not is_offline_intake,
        client_online=initiated_by == Dialog.InitiatedBy.CLIENT,
        client_last_seen_at=now if initiated_by == Dialog.InitiatedBy.CLIENT else None,
        last_client_message_at=now if initiated_by == Dialog.InitiatedBy.CLIENT else None,
        accepted_at=now if status == Dialog.Status.ACTIVE else None,
        outcome=Dialog.Outcome.OFFLINE if is_offline_intake else "",
    )
    speaker = (
        DialogMessage.Speaker.OPERATOR
        if initiated_by == Dialog.InitiatedBy.OPERATOR
        else DialogMessage.Speaker.CLIENT
    )
    delivery_status = DialogMessage.ChannelDeliveryStatus.NOT_REQUIRED
    if speaker == DialogMessage.Speaker.OPERATOR and dialog.channel != "widget":
        delivery_status = DialogMessage.ChannelDeliveryStatus.PENDING
    message = DialogMessage.objects.create(
        dialog=dialog,
        speaker=speaker,
        text=text.strip(),
        channel_delivery_status=delivery_status,
    )
    if is_offline_intake:
        # Operators are offline — send the configured "вне графика" notice (if any)
        # and skip the bot so the client isn't promised an immediate answer.
        _send_offline_notice(dialog, placement_config)
    else:
        base_messages_sent = _send_base_messages(
            dialog,
            BaseMessage.SendPhase.BEFORE_BOT,
            placement_config,
        )
        if not base_messages_sent and bot and bot.welcome_message:
            _create_bot_message(dialog, bot.welcome_message)
    record_event(
        dialog,
        "created",
        actor_name=operator_name if initiated_by == Dialog.InitiatedBy.OPERATOR else "client",
        payload={
            "widget_id": widget_id,
            "placement_id": str(placement_config.id) if placement_config else None,
            "routing_reason": routing_reason,
        },
    )
    if (
        status == Dialog.Status.WAITING
        and not dialog.bot_active
        and not queue_full
        and not is_offline_intake
        and not skip_auto_assign
    ):
        assigned = auto_assign_dialog(dialog)
        if assigned:
            dialog = assigned
    if (
        initiated_by == Dialog.InitiatedBy.CLIENT
        and dialog.status == Dialog.Status.WAITING
        and not dialog.bot_active
    ):
        _enqueue_hold_base_messages(dialog, placement_config)
    dialog_payload = serialize_dialog(dialog)
    message_payload = serialize_message(message)
    broadcast(ARM_GROUP, "dialog.created", dialog_payload)
    broadcast(dialog_group(str(dialog.id)), "message.created", message_payload)
    broadcast(ARM_GROUP, "message.created", message_payload)
    if delivery_status == DialogMessage.ChannelDeliveryStatus.PENDING:
        from online_chat.tasks import deliver_channel_message

        deliver_channel_message.delay(str(message.id))
    return dialog, message


def append_message(
    dialog: Dialog,
    *,
    speaker: str,
    text: str,
    reply_to: DialogMessage | None = None,
    attachment_name: str = "",
    attachment_key: str = "",
    attachment_content_type: str = "",
    attachment_size: int = 0,
    attachment_scan_status: str = "not_required",
    external_message_id: str = "",
    response_origin: str = "",
    sufler_suggestion_text: str = "",
) -> DialogMessage:
    cleaned = text.strip()
    quoted = ""
    if reply_to is not None:
        quoted = (reply_to.display_text() or "")[:500]
    if attachment_name and not cleaned:
        cleaned = f"Файл: {attachment_name}"
    receipt = DialogMessage.ReceiptStatus.DELIVERED
    delivery_status = DialogMessage.ChannelDeliveryStatus.NOT_REQUIRED
    if speaker == DialogMessage.Speaker.OPERATOR and dialog.channel != "widget":
        delivery_status = DialogMessage.ChannelDeliveryStatus.PENDING
    message = DialogMessage.objects.create(
        dialog=dialog,
        speaker=speaker,
        text=cleaned,
        reply_to=reply_to,
        quoted_text=quoted,
        attachment_name=attachment_name.strip(),
        attachment_key=attachment_key,
        attachment_content_type=attachment_content_type,
        attachment_size=max(0, attachment_size),
        attachment_scan_status=attachment_scan_status,
        external_message_id=external_message_id.strip(),
        response_origin=response_origin.strip(),
        sufler_suggestion_text=sufler_suggestion_text,
        channel_delivery_status=delivery_status,
        receipt_status=receipt,
    )
    update_fields = ["updated_at", "preview"]
    dialog.preview = cleaned[:500]
    if speaker == DialogMessage.Speaker.CLIENT:
        dialog.client_online = True
        dialog.client_last_seen_at = timezone.now()
        dialog.last_client_message_at = timezone.now()
        update_fields.extend(["client_online", "client_last_seen_at", "last_client_message_at"])
    elif speaker == DialogMessage.Speaker.OPERATOR and dialog.first_response_at is None:
        dialog.first_response_at = timezone.now()
        update_fields.append("first_response_at")
    dialog.save(update_fields=update_fields)
    operator_name = ""
    operator_avatar = ""
    operator_id = ""
    if speaker == DialogMessage.Speaker.OPERATOR:
        dialog = Dialog.objects.select_related("operator").get(pk=dialog.pk)
        operator_name = dialog.operator_name
        operator_id = str(dialog.operator_id) if dialog.operator_id else ""
        operator_avatar = _operator_avatar(dialog)
    payload = serialize_message(
        message,
        operator_name=operator_name,
        operator_avatar=operator_avatar,
        operator_id=operator_id,
    )
    broadcast(dialog_group(str(dialog.id)), "message.created", payload)
    broadcast(ARM_GROUP, "message.created", payload)
    # Backup path: client widget also POSTs /read/; if it was online but flag lagged,
    # still notify ARM when marks arrive later.
    if (
        speaker == DialogMessage.Speaker.OPERATOR
        and receipt == DialogMessage.ReceiptStatus.READ
    ):
        broadcast(
            ARM_GROUP,
            "messages.read",
            {
                "dialog_id": str(dialog.id),
                "reader": DialogMessage.Speaker.CLIENT,
                "message_ids": [str(message.id)],
                "messages": [payload],
            },
        )
    if delivery_status == DialogMessage.ChannelDeliveryStatus.PENDING:
        from online_chat.tasks import deliver_channel_message

        message_id = str(message.id)
        try:
            deliver_channel_message.delay(message_id)
        except Exception:  # noqa: BLE001 — broker down: deliver inline
            deliver_channel_message(message_id)
    if speaker == DialogMessage.Speaker.CLIENT and dialog.bot_active:
        _handle_bot_turn(dialog, cleaned)
        dialog.refresh_from_db(fields=["status", "outcome", "bot_active", "operator_id", "accepted_at"])
    if (
        speaker == DialogMessage.Speaker.CLIENT
        and dialog.status == Dialog.Status.WAITING
        and not dialog.bot_active
    ):
        placement_config = None
        if dialog.channel == "widget":
            placement_config = WidgetPlacement.objects.filter(widget_id=dialog.widget_id).first()
        _enqueue_hold_base_messages(dialog, placement_config)
    return message


def edit_message(message: DialogMessage, *, text: str) -> DialogMessage:
    cleaned = text.strip()
    # Attachment messages may keep an empty caption; file itself is unchanged.
    if not cleaned and not message.attachment_key:
        raise ValueError("text must be non-empty")
    if message.is_deleted:
        raise ValueError("message is deleted")
    if message.speaker == DialogMessage.Speaker.SYSTEM:
        raise ValueError("system messages cannot be edited")
    if not cleaned and message.attachment_name:
        cleaned = f"Файл: {message.attachment_name}"
    message.text = cleaned
    message.edited_at = timezone.now()
    # Keep receipt_status as-is (edit does not revoke delivery/read).
    # Attachment fields are intentionally preserved on text-only edits.
    message.save(update_fields=["text", "edited_at"])
    if message.speaker == DialogMessage.Speaker.CLIENT:
        dialog = message.dialog
        dialog.preview = cleaned[:500]
        dialog.save(update_fields=["preview", "updated_at"])
    elif message.speaker == DialogMessage.Speaker.OPERATOR:
        message.dialog.save(update_fields=["updated_at"])
    payload = serialize_message(message)
    broadcast(dialog_group(str(message.dialog_id)), "message.updated", payload)
    broadcast(ARM_GROUP, "message.updated", payload)
    return message


def delete_message(message: DialogMessage) -> DialogMessage:
    if message.speaker == DialogMessage.Speaker.SYSTEM:
        raise ValueError("system messages cannot be deleted")
    message.is_deleted = True
    message.text = ""
    message.edited_at = timezone.now()
    message.save(update_fields=["is_deleted", "text", "edited_at"])
    dialog = message.dialog
    last = _last_human_message(dialog)
    if last is not None:
        dialog.preview = last.display_text()[:500]
    else:
        dialog.preview = "—"
    dialog.save(update_fields=["preview", "updated_at"])
    payload = serialize_message(message)
    broadcast(dialog_group(str(message.dialog_id)), "message.updated", payload)
    broadcast(ARM_GROUP, "message.updated", payload)
    return message


def accept_dialog(dialog: Dialog, operator_name: str) -> Dialog:
    operator = OperatorProfile.objects.filter(
        display_name=operator_name,
        is_active=True,
    ).first()
    dialog = accept_waiting_dialog(
        dialog.pk,
        operator=operator,
        operator_name=operator_name,
    )
    system = DialogMessage.objects.create(
        dialog=dialog,
        speaker=DialogMessage.Speaker.SYSTEM,
        text=f"{operator_name} подключился к диалогу",
        receipt_status=DialogMessage.ReceiptStatus.READ,
    )
    dialog_payload = serialize_dialog(dialog)
    broadcast(ARM_GROUP, "dialog.updated", dialog_payload)
    broadcast(
        dialog_group(str(dialog.id)),
        "operator.joined",
        {
            **dialog_payload,
            "system_message": serialize_message(system),
        },
    )
    return dialog


def transfer_dialog(
    dialog: Dialog,
    *,
    to_operator_name: str,
    from_operator_name: str = "",
) -> Dialog:
    target = to_operator_name.strip()
    if not target:
        raise ValueError("to_operator_name is required")
    previous = dialog.operator_name or from_operator_name or "оператор"
    dialog = transfer_to_operator(dialog, operator_name=target)
    target_is_supervisor = OperatorProfile.objects.filter(
        display_name=target,
        role=OperatorProfile.Role.SUPERVISOR,
        is_active=True,
    ).exists()
    if previous and previous != target and target_is_supervisor:
        system_text = (
            f"К чату присоединился супервизор {target}. "
            f"Оператор {previous} отключился."
        )
    else:
        system_text = f"Диалог переведён: {previous} → {target}"
    system = DialogMessage.objects.create(
        dialog=dialog,
        speaker=DialogMessage.Speaker.SYSTEM,
        text=system_text,
        receipt_status=DialogMessage.ReceiptStatus.READ,
    )
    payload = serialize_dialog(dialog)
    broadcast(ARM_GROUP, "dialog.updated", payload)
    broadcast(
        dialog_group(str(dialog.id)),
        "dialog.transferred",
        {
            **payload,
            "system_message": serialize_message(system),
            "from_operator_name": previous,
            "to_operator_name": target,
        },
    )
    return dialog


def close_dialog(
    dialog: Dialog,
    *,
    topic: str,
    topic_node: DialogCloseTopicNode | None = None,
) -> Dialog:
    previous_operator = dialog.operator
    dialog.mark_closed(topic, topic_node=topic_node)
    record_event(dialog, "closed", actor_name=dialog.operator_name, payload={"topic": topic})
    system = DialogMessage.objects.create(
        dialog=dialog,
        speaker=DialogMessage.Speaker.SYSTEM,
        text="Диалог завершён",
        receipt_status=DialogMessage.ReceiptStatus.READ,
    )
    try:
        from online_chat.summary_service import ensure_dialog_summaries

        ensure_dialog_summaries(dialog, force=True)
    except Exception:  # noqa: BLE001
        logger.exception("dialog_summary_on_close_failed dialog_id=%s", dialog.id)
    # Manual+auto: grace window for the freed operator before auto-assign fills the slot.
    try:
        hold = start_post_close_grace(previous_operator)
    except Exception:  # noqa: BLE001 — never block close on grace/timer errors
        logger.exception("start_post_close_grace_failed operator=%s", getattr(previous_operator, "id", None))
        hold = None
    payload = serialize_dialog(dialog)
    if hold is not None:
        payload["assignment_grace_until"] = hold.until.isoformat()
        payload["assignment_grace_seconds"] = AssignmentSettings.GRACE_SECONDS
    broadcast(ARM_GROUP, "dialog.updated", payload)
    broadcast(
        dialog_group(str(dialog.id)),
        "dialog.closed",
        {
            **payload,
            "system_message": serialize_message(system),
            "farewell_message": "Спасибо за обращение! Диалог завершён.",
        },
    )
    if str(dialog.channel or "").lower() == "telegram":
        try:
            from online_chat.channel_delivery import send_telegram_close_survey

            send_telegram_close_survey(dialog)
        except Exception:  # noqa: BLE001
            logger.exception("telegram_close_survey_failed dialog_id=%s", dialog.id)
    return dialog


def mark_dialog_messages_read(
    dialog: Dialog,
    *,
    reader: str,
) -> list[DialogMessage]:
    """Mark the other party's unread messages as read (1✓ → 2✓)."""
    if reader == DialogMessage.Speaker.CLIENT:
        target_speaker = DialogMessage.Speaker.OPERATOR
    elif reader == DialogMessage.Speaker.OPERATOR:
        target_speaker = DialogMessage.Speaker.CLIENT
    else:
        return []

    qs = dialog.messages.filter(
        speaker=target_speaker,
        receipt_status=DialogMessage.ReceiptStatus.DELIVERED,
        is_deleted=False,
    )
    message_ids = list(qs.values_list("id", flat=True))
    if not message_ids:
        return []
    qs.update(receipt_status=DialogMessage.ReceiptStatus.READ)
    updated = list(dialog.messages.filter(id__in=message_ids))
    payload = {
        "dialog_id": str(dialog.id),
        "reader": reader,
        "message_ids": [str(item.id) for item in updated],
        "messages": [serialize_message(item) for item in updated],
    }
    broadcast(dialog_group(str(dialog.id)), "messages.read", payload)
    broadcast(ARM_GROUP, "messages.read", payload)
    return updated


def set_client_presence(dialog: Dialog, *, online: bool) -> Dialog:
    dialog.client_online = online
    dialog.client_last_seen_at = timezone.now()
    if not online and dialog.status not in {Dialog.Status.CLOSED, Dialog.Status.BLOCKED}:
        dialog.outcome = Dialog.Outcome.OFFLINE
    elif online and dialog.outcome == Dialog.Outcome.OFFLINE:
        dialog.outcome = ""
    dialog.save(
        update_fields=[
            "client_online",
            "client_last_seen_at",
            "outcome",
            "updated_at",
        ]
    )
    payload = serialize_dialog(dialog)
    broadcast(ARM_GROUP, "dialog.updated", payload)
    broadcast(dialog_group(str(dialog.id)), "client.presence", payload)
    return dialog


def block_dialog(
    dialog: Dialog,
    *,
    blocked_by: str = "",
    reason: str = "",
) -> tuple[Dialog, ClientBlock | None]:
    phone = dialog.client_phone
    block: ClientBlock | None = None
    normalized = normalize_phone(phone)
    if normalized:
        block = ClientBlock.objects.create(
            phone=phone,
            phone_normalized=normalized,
            reason=reason.strip() or "Заблокирован оператором в онлайн-чате",
            blocked_by=blocked_by.strip() or dialog.operator_name or "operator",
            dialog=dialog,
            is_active=True,
        )
        _emit_block_audit(
            event_type=ONLINE_CHAT_CLIENT_BLOCKED,
            description=f"Client blocked in online chat ({normalized})",
            details={
                "dialog_id": str(dialog.id),
                "phone_normalized": normalized,
                "blocked_by": block.blocked_by,
                "reason": block.reason,
            },
        )

    dialog.mark_blocked()
    record_event(dialog, "blocked", actor_name=blocked_by, payload={"reason": reason})
    system = DialogMessage.objects.create(
        dialog=dialog,
        speaker=DialogMessage.Speaker.SYSTEM,
        text="Клиент заблокирован. Диалог завершён.",
        receipt_status=DialogMessage.ReceiptStatus.READ,
    )
    payload = serialize_dialog(dialog)
    broadcast(ARM_GROUP, "dialog.updated", payload)
    broadcast(
        dialog_group(str(dialog.id)),
        "dialog.blocked",
        {
            **payload,
            "system_message": serialize_message(system),
            "farewell_message": "Обращение недоступно. При необходимости обратитесь в отделение банка.",
        },
    )
    return dialog, block


def unblock_client(block: ClientBlock, *, lifted_by: str = "") -> ClientBlock:
    block.is_active = False
    block.lifted_at = timezone.now()
    block.save(update_fields=["is_active", "lifted_at"])
    _emit_block_audit(
        event_type=ONLINE_CHAT_CLIENT_UNBLOCKED,
        description=f"Client unblocked in online chat ({block.phone_normalized})",
        details={
            "block_id": str(block.id),
            "phone_normalized": block.phone_normalized,
            "lifted_by": lifted_by or "admin",
        },
    )
    return block


def save_feedback(
    dialog: Dialog,
    *,
    rating: int,
    comment: str = "",
) -> DialogFeedback:
    feedback, _created = DialogFeedback.objects.update_or_create(
        dialog=dialog,
        defaults={
            "rating": rating,
            "comment": comment.strip(),
        },
    )
    return feedback


def request_transcript_email(dialog: Dialog, *, email: str) -> DialogTranscriptEmail:
    return send_dialog_transcript(dialog, email=email)
