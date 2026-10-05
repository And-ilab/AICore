"""Prometheus text metrics for TEST/PROD ops (no prometheus_client dep)."""

from __future__ import annotations

from django.http import HttpResponse
from django.views.decorators.http import require_GET

from core.health import collect_health


@require_GET
def metrics(request) -> HttpResponse:
    """GET /metrics/ — Prometheus exposition format for scrape targets."""
    payload = collect_health()
    ok = 1 if payload["ok"] else 0
    db_ok = 1 if payload["checks"]["database"].get("status") == "ok" else 0
    redis_ok = 1 if payload["checks"]["redis"].get("status") == "ok" else 0

    lines = [
        "# HELP sufler_up Always 1 when the metrics process responds.",
        "# TYPE sufler_up gauge",
        "sufler_up 1",
        "# HELP sufler_health_ok 1 when GET /health/ would return HTTP 200.",
        "# TYPE sufler_health_ok gauge",
        f"sufler_health_ok {ok}",
        "# HELP sufler_health_check Dependency probe (1=ok).",
        "# TYPE sufler_health_check gauge",
        f'sufler_health_check{{component="database"}} {db_ok}',
        f'sufler_health_check{{component="redis"}} {redis_ok}',
        "",
    ]
    body = "\n".join(lines)
    return HttpResponse(body, content_type="text/plain; version=0.0.4; charset=utf-8")
