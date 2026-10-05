"""Telegram getUpdates long polling (test contour without HTTPS/ngrok)."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings
from django.db import close_old_connections

from integrations.channels.webhooks import ChannelWebhookError, handle_telegram_update

logger = logging.getLogger(__name__)


def _bot_api(method: str, *, http_timeout: float, **params: Any) -> dict[str, Any]:
    token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is empty")
    url = f"https://api.telegram.org/bot{token}/{method}"
    if params:
        query = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
        url = f"{url}?{query}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=http_timeout) as response:  # noqa: S310
        body = response.read()
    return json.loads(body or b"{}")


def delete_webhook(*, drop_pending: bool = True) -> dict[str, Any]:
    return _bot_api(
        "deleteWebhook",
        http_timeout=20,
        drop_pending_updates="true" if drop_pending else "false",
    )


def get_updates(
    *,
    offset: int | None,
    timeout_seconds: int,
) -> list[dict[str, Any]]:
    # HTTP timeout must exceed Telegram long-poll timeout.
    http_timeout = float(timeout_seconds) + 15.0
    params: dict[str, Any] = {
        "timeout": timeout_seconds,
        "allowed_updates": json.dumps(["message", "edited_message", "callback_query"]),
    }
    if offset is not None:
        params["offset"] = offset
    body = _bot_api("getUpdates", http_timeout=http_timeout, **params)
    if not body.get("ok"):
        raise RuntimeError(f"getUpdates failed: {body}")
    result = body.get("result") or []
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, dict)]


def process_update(update: dict[str, Any]) -> dict[str, Any] | None:
    """Dispatch one Telegram update through the same handler as the webhook."""
    update_id = update.get("update_id")
    try:
        result = handle_telegram_update(update)
        logger.info(
            "telegram_poll handled update_id=%s routed_to=%s",
            update_id,
            (result or {}).get("routed_to"),
        )
        return result
    except ChannelWebhookError as exc:
        # Stickers / empty captions / unsupported payloads — skip.
        logger.info("telegram_poll skip update_id=%s detail=%s", update_id, exc)
        return None
    except Exception:  # noqa: BLE001 — keep polling alive
        logger.exception("telegram_poll failed update_id=%s", update_id)
        return None


def run_polling_loop(
    *,
    timeout_seconds: int | None = None,
    idle_backoff_seconds: float = 3.0,
) -> None:
    """Block forever: deleteWebhook, then long-poll getUpdates."""
    timeout_seconds = int(
        timeout_seconds
        if timeout_seconds is not None
        else getattr(settings, "TELEGRAM_POLL_TIMEOUT_SECONDS", 25)
    )
    logger.info(
        "telegram_poll starting (timeout=%ss); clearing webhook if any",
        timeout_seconds,
    )
    try:
        deleted = delete_webhook(drop_pending=True)
        logger.info("telegram_poll deleteWebhook: %s", deleted.get("ok"))
    except Exception:  # noqa: BLE001
        logger.exception("telegram_poll deleteWebhook failed; continuing")

    offset: int | None = None
    while True:
        # Drop any stale/broken DB connection so a Postgres hiccup does not
        # permanently wedge the poller ("the connection is closed").
        close_old_connections()
        try:
            updates = get_updates(offset=offset, timeout_seconds=timeout_seconds)
        except urllib.error.HTTPError as exc:
            logger.warning("telegram_poll HTTP %s; backoff %.1fs", exc.code, idle_backoff_seconds)
            close_old_connections()
            time.sleep(idle_backoff_seconds)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("telegram_poll getUpdates error; backoff %.1fs", idle_backoff_seconds)
            close_old_connections()
            time.sleep(idle_backoff_seconds)
            continue

        for update in updates:
            update_id = update.get("update_id")
            if isinstance(update_id, int):
                offset = update_id + 1
            close_old_connections()
            process_update(update)
