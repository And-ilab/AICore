"""Inbound adapters for widget, messengers, social networks, and API."""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Any, Mapping

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from online_chat.models import Dialog, DialogMessage
from online_chat.services import append_message, create_dialog_with_message

# In-memory inbox for local demos / CHAT-T-12 style checks.
_INBOX: list[dict[str, Any]] = []


class ChannelWebhookError(ValueError):
    """Invalid messenger webhook payload."""


def reset_inbox() -> None:
    _INBOX.clear()


def list_inbox() -> list[dict[str, Any]]:
    return list(_INBOX)


def _json_body(request: HttpRequest) -> Mapping[str, Any]:
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ChannelWebhookError("Request body must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ChannelWebhookError("Request body must be a JSON object")
    return payload


def _store(
    *,
    channel: str,
    external_user_id: str,
    text: str,
    raw: Mapping[str, Any],
    placement: str | None = None,
) -> dict[str, Any]:
    existing = (
        Dialog.objects.filter(
            channel=channel,
            client_external_id=external_user_id,
            status__in=(Dialog.Status.WAITING, Dialog.Status.ACTIVE),
        )
        .order_by("-updated_at")
        .first()
    )
    external_message_id = str(
        raw.get("update_id")
        or raw.get("message_token")
        or raw.get("event_id")
        or ""
    )
    if existing:
        message = append_message(
            existing,
            speaker=DialogMessage.Speaker.CLIENT,
            text=text,
            external_message_id=external_message_id,
        )
        dialog = existing
    else:
        dialog, message = create_dialog_with_message(
            text=text,
            channel=channel,
            widget_id="",
            placement=(placement or channel),
            client_first_name=str(raw.get("client_name") or channel.title()),
            client_external_id=external_user_id,
            entry_url=str(raw.get("page_url") or ""),
            locale=str(raw.get("locale") or "ru"),
        )
        if external_message_id:
            message.external_message_id = external_message_id
            message.save(update_fields=["external_message_id"])
    event = {
        "id": str(uuid.uuid4()),
        "dialog_id": str(dialog.id),
        "message_id": str(message.id),
        "channel": channel,
        "external_user_id": external_user_id,
        "text": text,
        "routed_to": "arm_queue",
        "raw": dict(raw),
    }
    _INBOX.append(event)
    return event


def handle_telegram_update(payload: Mapping[str, Any]) -> dict[str, Any]:
    from online_chat.channel_delivery import answer_telegram_callback, send_telegram_text
    from online_chat.models import Dialog
    from online_chat.services import save_feedback
    from online_chat.telegram_onboarding import handle_telegram_client_text

    callback = payload.get("callback_query")
    if isinstance(callback, Mapping):
        data = str(callback.get("data") or "")
        callback_id = str(callback.get("id") or "")
        parts = data.split(":")
        if len(parts) == 3 and parts[0] == "rate":
            dialog_id, rating_raw = parts[1], parts[2]
            try:
                rating = int(rating_raw)
            except ValueError:
                rating = 0
            # Accept compact uuid (without dashes) or canonical form.
            compact = dialog_id.replace("-", "")
            dialog = None
            if len(compact) == 32:
                from uuid import UUID

                try:
                    dialog = Dialog.objects.filter(pk=UUID(hex=compact)).first()
                except ValueError:
                    dialog = None
            if dialog is None:
                dialog = Dialog.objects.filter(pk=dialog_id).first()
            if dialog is None or rating < 1 or rating > 5:
                answer_telegram_callback(callback_id, "Не удалось сохранить оценку.")
                return {"ok": True, "channel": "telegram", "routed_to": "rating_ignored"}
            save_feedback(dialog, rating=rating, comment="telegram_inline")
            answer_telegram_callback(callback_id, "Спасибо за оценку!")
            chat = (callback.get("message") or {}).get("chat") or {}
            chat_id = str(chat.get("id") or dialog.client_external_id or "")
            if chat_id:
                send_telegram_text(
                    chat_id,
                    f"Спасибо! Ваша оценка: {rating}/5. Хорошего дня!",
                )
            return {
                "ok": True,
                "channel": "telegram",
                "routed_to": "rating_saved",
                "dialog_id": str(dialog.id),
                "rating": rating,
            }
        if parts and parts[0] == "skip_field":
            from online_chat.telegram_onboarding import handle_telegram_skip_field

            chat = (callback.get("message") or {}).get("chat") or {}
            chat_id = str(chat.get("id") or "")
            answer_telegram_callback(callback_id, "Поле пропущено")
            if chat_id:
                return handle_telegram_skip_field(chat_id=chat_id)
            return {"ok": True, "channel": "telegram", "routed_to": "skip_ignored"}
        answer_telegram_callback(callback_id)
        return {"ok": True, "channel": "telegram", "routed_to": "callback_ignored"}

    message = payload.get("message") or payload.get("edited_message") or {}
    if not isinstance(message, Mapping):
        raise ChannelWebhookError("telegram payload requires message object")
    text = message.get("text") or message.get("caption") or ""
    if not isinstance(text, str) or not text.strip():
        raise ChannelWebhookError("telegram message text is required")
    chat = message.get("chat") or {}
    user = message.get("from") or {}
    external_id = str(
        (chat.get("id") if isinstance(chat, Mapping) else None)
        or (user.get("id") if isinstance(user, Mapping) else None)
        or "unknown"
    )
    return handle_telegram_client_text(
        chat_id=external_id,
        text=text.strip(),
        raw=payload,
    )


def handle_viber_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("event") or "message")
    if event_type in {"webhook", "subscribed", "unsubscribed", "conversation_started"}:
        return {"ok": True, "channel": "viber", "event": event_type, "status": 0}
    message = payload.get("message") or {}
    if not isinstance(message, Mapping):
        raise ChannelWebhookError("viber payload requires message object")
    text = message.get("text") or ""
    if not isinstance(text, str) or not text.strip():
        raise ChannelWebhookError("viber message text is required")
    sender = payload.get("sender") or {}
    external_id = str(
        (sender.get("id") if isinstance(sender, Mapping) else None) or "unknown"
    )
    event = _store(
        channel="viber",
        external_user_id=external_id,
        text=text.strip(),
        raw=payload,
    )
    return {
        "ok": True,
        "channel": "viber",
        "event_id": event["id"],
        "routed_to": "arm_queue",
        "status": 0,
        "reply": {
            "type": "text",
            "text": "Сообщение принято (mock Viber). Оператор ответит в АРМ.",
        },
    }


def handle_vk_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(payload.get("type") or "")
    if event_type != "message_new":
        return {"ok": True, "ignored": True, "type": event_type}
    obj = payload.get("object") or {}
    message = obj.get("message") if isinstance(obj, Mapping) else {}
    if not isinstance(message, Mapping):
        raise ChannelWebhookError("vk object.message is required")
    text = str(message.get("text") or "").strip()
    user_id = str(message.get("peer_id") or message.get("from_id") or "")
    if not text or not user_id:
        raise ChannelWebhookError("vk message text and sender are required")
    event = _store(
        channel="vk",
        external_user_id=user_id,
        text=text,
        placement="vk",
        raw={**dict(payload), "event_id": payload.get("event_id")},
    )
    return {"ok": True, "channel": "vk", "event": event, "routed_to": "arm_queue"}


def handle_ok_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    message = payload.get("message") or payload.get("object") or payload
    if not isinstance(message, Mapping):
        raise ChannelWebhookError("ok message object is required")
    text = str(message.get("text") or message.get("message") or "").strip()
    user_id = str(
        message.get("sender_id")
        or message.get("user_id")
        or message.get("from")
        or ""
    )
    if not text or not user_id:
        raise ChannelWebhookError("ok message text and sender are required")
    event = _store(
        channel="ok",
        external_user_id=user_id,
        text=text,
        placement="ok",
        raw=dict(payload),
    )
    return {"ok": True, "channel": "ok", "event": event, "routed_to": "arm_queue"}


def handle_api_event(payload: Mapping[str, Any]) -> dict[str, Any]:
    text = str(payload.get("text") or "").strip()
    client_id = str(payload.get("client_external_id") or payload.get("client_id") or "")
    if not text or not client_id:
        raise ChannelWebhookError("text and client_external_id are required")
    event = _store(
        channel="api",
        external_user_id=client_id,
        text=text,
        placement=str(payload.get("placement") or "api"),
        raw=dict(payload),
    )
    return {"ok": True, "channel": "api", "event": event, "routed_to": "arm_queue"}


def handle_widget_message(
    widget_id: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    text = payload.get("text") or ""
    if not isinstance(text, str) or not text.strip():
        raise ChannelWebhookError("text must be a non-empty string")
    if not widget_id.strip():
        raise ChannelWebhookError("widget_id is required")
    placement = str(payload.get("placement") or "website")
    external_user_id = str(
        payload.get("client_external_id")
        or payload.get("session_id")
        or uuid.uuid4()
    )
    event = _store(
        channel="widget",
        external_user_id=external_user_id,
        text=text.strip(),
        raw={**dict(payload), "widget_id": widget_id, "placement": placement},
    )
    return {
        "ok": True,
        "channel": "widget",
        "widget_id": widget_id,
        "placement": placement,
        "event_id": event["id"],
        "routed_to": "arm_queue",
        "reply": (
            "Спасибо! Ваше сообщение принято виджетом "
            f"«{widget_id}». Оператор ответит в ближайшее время."
        ),
    }


def _error(exc: ChannelWebhookError) -> JsonResponse:
    return JsonResponse(
        {"ok": False, "error": "validation_error", "detail": str(exc)},
        status=400,
    )


@csrf_exempt
@require_http_methods(["POST"])
def telegram_webhook(request: HttpRequest) -> JsonResponse:
    try:
        return JsonResponse(handle_telegram_update(_json_body(request)))
    except ChannelWebhookError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def viber_webhook(request: HttpRequest) -> JsonResponse:
    try:
        return JsonResponse(handle_viber_event(_json_body(request)))
    except ChannelWebhookError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def vk_webhook(request: HttpRequest) -> HttpResponse:
    try:
        payload = _json_body(request)
        expected_secret = getattr(settings, "VK_WEBHOOK_SECRET", "")
        if expected_secret and not hmac.compare_digest(
            str(payload.get("secret") or ""),
            expected_secret,
        ):
            return JsonResponse({"ok": False, "detail": "invalid secret"}, status=403)
        if payload.get("type") == "confirmation":
            confirmation = getattr(settings, "VK_CONFIRMATION_CODE", "")
            return HttpResponse(confirmation or "ok", content_type="text/plain")
        return JsonResponse(handle_vk_event(payload))
    except ChannelWebhookError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def ok_webhook(request: HttpRequest) -> JsonResponse:
    expected_secret = getattr(settings, "OK_WEBHOOK_SECRET", "")
    supplied_secret = request.headers.get("X-Webhook-Secret", "")
    if expected_secret and not hmac.compare_digest(supplied_secret, expected_secret):
        return JsonResponse({"ok": False, "detail": "invalid secret"}, status=403)
    try:
        return JsonResponse(handle_ok_event(_json_body(request)))
    except ChannelWebhookError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def api_webhook(request: HttpRequest) -> JsonResponse:
    secret = getattr(settings, "ONLINE_CHAT_API_CHANNEL_SIGNING_SECRET", "")
    signature = request.headers.get("X-Online-Chat-Signature", "")
    if secret:
        expected = hmac.new(
            secret.encode(),
            request.body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return JsonResponse({"ok": False, "detail": "invalid signature"}, status=403)
    try:
        return JsonResponse(handle_api_event(_json_body(request)))
    except ChannelWebhookError as exc:
        return _error(exc)


@csrf_exempt
@require_http_methods(["POST"])
def widget_message(request: HttpRequest, widget_id: str) -> JsonResponse:
    try:
        return JsonResponse(handle_widget_message(widget_id, _json_body(request)))
    except ChannelWebhookError as exc:
        return _error(exc)


@require_http_methods(["GET"])
def channel_inbox(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"items": list_inbox(), "count": len(_INBOX)})
