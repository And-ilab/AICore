"""Application health for TEST/PROD probes (Django + Daphne + Redis)."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET


def _redis_url() -> str | None:
    """Return a Redis URL only when Redis is intentionally configured."""
    explicit = os.getenv("REDIS_URL", "").strip()
    if explicit:
        return explicit
    if os.getenv("REDIS_HOST"):
        host = os.environ["REDIS_HOST"]
        port = os.getenv("REDIS_PORT", "6379")
        password = os.getenv("REDIS_PASSWORD", "")
        auth = f":{password}@" if password else ""
        return f"redis://{auth}{host}:{port}/0"

    # Prefer channel-layer host when Channels is wired to Redis (TEST/PROD).
    layer = getattr(settings, "CHANNEL_LAYERS", {}).get("default", {})
    backend = layer.get("BACKEND", "")
    if "RedisChannelLayer" in backend:
        hosts = (layer.get("CONFIG") or {}).get("hosts") or []
        if hosts:
            first = hosts[0]
            if isinstance(first, str) and first.startswith(("redis://", "rediss://")):
                return first
        broker = getattr(settings, "CELERY_BROKER_URL", "") or ""
        if isinstance(broker, str) and broker.startswith(("redis://", "rediss://")):
            return broker
    return None


def _check_database() -> dict[str, Any]:
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"status": "ok"}
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        return {"status": "error", "detail": str(exc)[:200]}


def _check_redis() -> dict[str, Any]:
    url = _redis_url()
    if not url:
        backend = (
            settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
            if getattr(settings, "CHANNEL_LAYERS", None)
            else ""
        )
        if "InMemoryChannelLayer" in backend:
            return {"status": "ok", "detail": "inmemory_channel_layer"}
        return {"status": "ok", "detail": "not_configured"}

    try:
        import redis
    except ImportError:
        return {"status": "error", "detail": "redis package missing"}

    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        if client.ping() is not True:
            return {"status": "error", "detail": "ping_failed"}
        # Do not echo credentials / full URL.
        parsed = urlparse(url)
        return {
            "status": "ok",
            "host": parsed.hostname or "unknown",
            "port": parsed.port or 6379,
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": str(exc)[:200]}


def collect_health() -> dict[str, Any]:
    """Shared health payload for /health/ and /metrics/."""
    checks = {
        "database": _check_database(),
        "redis": _check_redis(),
    }
    ok = all(item.get("status") == "ok" for item in checks.values())
    channel_backend = (
        settings.CHANNEL_LAYERS.get("default", {}).get("BACKEND", "")
        if getattr(settings, "CHANNEL_LAYERS", None)
        else ""
    )
    return {
        "ok": ok,
        "checks": checks,
        "service": "sufler-backend",
        "asgi": "daphne",
        "channel_layer": channel_backend.rsplit(".", 1)[-1] or channel_backend,
    }


@require_GET
def health(request) -> JsonResponse:
    """GET /health/ — 200 when database and redis probes pass."""
    payload = collect_health()
    body = {
        "status": "ok" if payload["ok"] else "degraded",
        "checks": payload["checks"],
        "service": payload["service"],
        "asgi": payload["asgi"],
        "channel_layer": payload["channel_layer"],
    }
    return JsonResponse(body, status=200 if payload["ok"] else 503)
