"""Outbound text-channel delivery with environment-backed credentials."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from urllib.parse import urlencode
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from online_chat.models import ChannelConnection, DialogMessage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    sent: bool
    external_message_id: str = ""
    detail: str = ""


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    timeout = getattr(settings, "ONLINE_CHAT_CHANNEL_HTTP_TIMEOUT_SECONDS", 10)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read()
    return json.loads(body or b"{}")


def _post_form(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urlencode(payload).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    timeout = getattr(settings, "ONLINE_CHAT_CHANNEL_HTTP_TIMEOUT_SECONDS", 10)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read()
    return json.loads(body or b"{}")


def send_telegram_text(
    chat_id: str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> DeliveryResult:
    """Send a Telegram Bot API message (optionally with inline keyboard)."""
    token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if not token:
        return DeliveryResult(False, detail="telegram_not_configured")
    if not chat_id or not (text or "").strip():
        return DeliveryResult(False, detail="telegram_empty")
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text.strip()}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        body = _post_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            payload,
        )
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = (exc.read() or b"").decode("utf-8", errors="replace")[:300]
        except Exception:  # noqa: BLE001
            detail = str(exc)[:200]
        logger.warning(
            "telegram_send_failed chat=%s status=%s detail=%s",
            chat_id,
            exc.code,
            detail or exc,
        )
        return DeliveryResult(False, detail=detail or str(exc.code))
    except Exception as exc:  # noqa: BLE001 — onboarding must not crash webhook
        logger.warning("telegram_send_failed chat=%s detail=%s", chat_id, exc)
        return DeliveryResult(False, detail=str(exc)[:200])
    if not body.get("ok"):
        logger.warning(
            "telegram_send_rejected chat=%s detail=%s",
            chat_id,
            body.get("description") or body,
        )
        return DeliveryResult(False, detail="telegram_rejected")
    result = body.get("result") or {}
    return DeliveryResult(True, str(result.get("message_id") or ""))


def send_telegram_close_survey(dialog: Any) -> DeliveryResult:
    """After operator closes a Telegram dialog — farewell + 1..5 rating buttons."""
    chat_id = str(getattr(dialog, "client_external_id", "") or "").strip()
    dialog_id = str(getattr(dialog, "id", "") or "").replace("-", "")
    if not chat_id or not dialog_id:
        return DeliveryResult(False, detail="telegram_no_chat")
    # callback_data max 64 bytes — compact uuid without dashes.
    keyboard = {
        "inline_keyboard": [
            [
                {"text": f"{n}⭐", "callback_data": f"rate:{dialog_id}:{n}"}
                for n in range(1, 6)
            ]
        ]
    }
    result = send_telegram_text(
        chat_id,
        "Диалог завершён. Спасибо за обращение!\n"
        "Оцените, пожалуйста, работу оператора:",
        reply_markup=keyboard,
    )
    if not result.sent:
        logger.warning("telegram_close_survey_failed chat=%s detail=%s", chat_id, result.detail)
    return result


def answer_telegram_callback(callback_query_id: str, text: str = "") -> DeliveryResult:
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    if not token or not callback_query_id:
        return DeliveryResult(False, detail="telegram_not_configured")
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    try:
        body = _post_json(
            f"https://api.telegram.org/bot{token}/answerCallbackQuery",
            payload,
        )
    except Exception as exc:  # noqa: BLE001
        return DeliveryResult(False, detail=str(exc)[:200])
    if not body.get("ok"):
        return DeliveryResult(False, detail="telegram_rejected")
    return DeliveryResult(True)


def _telegram(message: DialogMessage) -> DeliveryResult:
    return send_telegram_text(message.dialog.client_external_id, message.text)


def _viber(message: DialogMessage) -> DeliveryResult:
    token = getattr(settings, "VIBER_AUTH_TOKEN", "")
    if not token:
        return DeliveryResult(False, detail="viber_not_configured")
    body = _post_json(
        "https://chatapi.viber.com/pa/send_message",
        {
            "receiver": message.dialog.client_external_id,
            "type": "text",
            "text": message.text,
        },
        headers={"X-Viber-Auth-Token": token},
    )
    if int(body.get("status", -1)) != 0:
        return DeliveryResult(False, detail="viber_rejected")
    return DeliveryResult(True, str(body.get("message_token") or ""))


def _api_channel(message: DialogMessage) -> DeliveryResult:
    connection = (
        ChannelConnection.objects.filter(channel="api", is_active=True)
        .order_by("created_at")
        .first()
    )
    config = connection.config if connection and isinstance(connection.config, dict) else {}
    endpoint = str(config.get("outbound_url") or config.get("endpoint") or "")
    secret = getattr(settings, "ONLINE_CHAT_API_CHANNEL_SIGNING_SECRET", "")
    if not endpoint:
        return DeliveryResult(False, detail="api_channel_not_configured")
    payload = {
        "dialog_id": str(message.dialog_id),
        "client_external_id": message.dialog.client_external_id,
        "message_id": str(message.id),
        "text": message.text,
        "created_at": message.created_at.isoformat(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers: dict[str, str] = {}
    if secret:
        headers["X-Online-Chat-Signature"] = hmac.new(
            secret.encode(), encoded, hashlib.sha256
        ).hexdigest()
    body = _post_json(endpoint, payload, headers=headers)
    return DeliveryResult(
        True,
        str(body.get("message_id") or body.get("id") or ""),
    )


def _vk(message: DialogMessage) -> DeliveryResult:
    token = getattr(settings, "VK_ACCESS_TOKEN", "")
    if not token:
        return DeliveryResult(False, detail="vk_not_configured")
    body = _post_form(
        "https://api.vk.com/method/messages.send",
        {
            "access_token": token,
            "v": "5.199",
            "peer_id": message.dialog.client_external_id,
            "message": message.text,
            "random_id": int(message.id.int % 2_147_483_647),
        },
    )
    if body.get("error"):
        return DeliveryResult(False, detail="vk_rejected")
    return DeliveryResult(True, str(body.get("response") or ""))


def _ok(message: DialogMessage) -> DeliveryResult:
    connection = (
        ChannelConnection.objects.filter(channel="ok", is_active=True)
        .order_by("created_at")
        .first()
    )
    config = connection.config if connection and isinstance(connection.config, dict) else {}
    endpoint = str(config.get("outbound_url") or "")
    token = getattr(settings, "OK_ACCESS_TOKEN", "")
    if not endpoint or not token:
        return DeliveryResult(False, detail="ok_not_configured")
    body = _post_json(
        endpoint,
        {
            "recipient_id": message.dialog.client_external_id,
            "text": message.text,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    return DeliveryResult(True, str(body.get("message_id") or body.get("id") or ""))


def deliver_message(message: DialogMessage) -> DeliveryResult:
    channel = message.dialog.channel
    if channel == "widget":
        return DeliveryResult(True)
    if channel == "telegram":
        return _telegram(message)
    if channel == "viber":
        return _viber(message)
    if channel == "api":
        return _api_channel(message)
    if channel == "vk":
        return _vk(message)
    if channel == "ok":
        return _ok(message)
    return DeliveryResult(False, detail=f"{channel}_adapter_not_configured")


def _get_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    timeout = getattr(settings, "ONLINE_CHAT_CHANNEL_HTTP_TIMEOUT_SECONDS", 10)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        body = response.read()
    return json.loads(body or b"{}")


def probe_channel(connection: ChannelConnection) -> tuple[str, str]:
    """Return (health_status, detail) without sending a client message."""
    channel = connection.channel
    if channel == ChannelConnection.Channel.WIDGET:
        return "ok", "widget_local"
    if channel == ChannelConnection.Channel.TELEGRAM:
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if not token:
            return "not_configured", "telegram_not_configured"
        try:
            body = _get_json(f"https://api.telegram.org/bot{token}/getMe")
            return ("ok", "telegram_ok") if body.get("ok") else ("error", "telegram_rejected")
        except Exception:  # noqa: BLE001
            return "error", "telegram_unreachable"
    if channel == ChannelConnection.Channel.VIBER:
        token = getattr(settings, "VIBER_AUTH_TOKEN", "")
        return ("ok", "viber_token_present") if token else ("not_configured", "viber_not_configured")
    if channel == ChannelConnection.Channel.VK:
        token = getattr(settings, "VK_ACCESS_TOKEN", "")
        return ("ok", "vk_token_present") if token else ("not_configured", "vk_not_configured")
    if channel == ChannelConnection.Channel.OK:
        token = getattr(settings, "OK_ACCESS_TOKEN", "")
        config = connection.config if isinstance(connection.config, dict) else {}
        endpoint = str(config.get("outbound_url") or "")
        if token and endpoint:
            return "ok", "ok_token_present"
        return "not_configured", "ok_not_configured"
    if channel == ChannelConnection.Channel.API:
        config = connection.config if isinstance(connection.config, dict) else {}
        endpoint = str(config.get("outbound_url") or config.get("endpoint") or "")
        return ("ok", "api_endpoint_present") if endpoint else ("not_configured", "api_channel_not_configured")
    return "unknown", f"{channel}_adapter_not_configured"
