from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from kombu.exceptions import OperationalError

from ingest.bitrix_client import ingest_mode
from ingest.pipeline import checksum_for_text, normalize_text
from ingest.reconcile import get_or_create_state, run_reconciliation
from ingest.schema import SuzPayload, SuzPayloadError
from ingest.signature import verify_hmac_signature
from ingest.tasks import enqueue_ingest_chain, reconcile_suz_changes


@csrf_exempt
@require_POST
def knowledge_events(request: HttpRequest) -> JsonResponse:
    """Receive SUZ Model B events for INT-01..05 and INT-07."""
    secret = settings.SUZ_WEBHOOK_HMAC_SECRET
    if ingest_mode() == "prod" and not secret:
        return JsonResponse(
            {
                "error": "misconfigured",
                "detail": (
                    "SUZ_WEBHOOK_HMAC_SECRET is required when SUZ_INGEST_MODE=prod"
                ),
            },
            status=503,
        )
    # HMAC required whenever secret is set (mock with secret or prod).
    if secret and not verify_hmac_signature(
        request.body,
        request.headers.get("X-Sufler-Signature", ""),
        secret,
    ):
        return JsonResponse({"error": "auth"}, status=401)

    try:
        raw_payload = json.loads(request.body)
        if not isinstance(raw_payload, dict):
            raise ValueError
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return JsonResponse(
            {"error": "validation", "fields": ["body"]},
            status=400,
        )

    try:
        payload = SuzPayload.from_mapping(raw_payload)
        header_event_id = request.headers.get("X-Sufler-Event-Id")
        if header_event_id and header_event_id != str(payload.event_id):
            raise SuzPayloadError(["X-Sufler-Event-Id"])
        allowed_iblocks = getattr(settings, "SUZ_ALLOWED_IBLOCK_IDS", frozenset())
        if allowed_iblocks and payload.iblock_id not in allowed_iblocks:
            raise SuzPayloadError(["iblock_id"])
        if (
            payload.event_type == "article.version_published"
            and checksum_for_text(
                normalize_text(payload.body_plain, payload.body_html)
            )
            != payload.checksum
        ):
            raise SuzPayloadError(["checksum"])
    except SuzPayloadError as exc:
        return JsonResponse(
            {"error": "validation", "fields": exc.fields},
            status=400,
        )

    try:
        result = enqueue_ingest_chain(raw_payload)
    except OperationalError:
        return JsonResponse({"error": "temporary"}, status=503)

    return JsonResponse(
        {
            "status": "accepted",
            "event_id": str(payload.event_id),
            "outcome": "queued",
            "task_id": result.id,
            "ingest_mode": ingest_mode(),
        },
        status=202,
    )


@require_GET
def knowledge_reconcile_status(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/knowledge/reconcile/ — INT-09 cursor status."""
    state = get_or_create_state()
    return JsonResponse(
        {
            "mode": ingest_mode(),
            "model": "B",
            "acceptance": ["INT-09", "INT-T-SUZ"],
            "cursor": state.cursor,
            "last_run_at": (
                state.last_run_at.isoformat() if state.last_run_at else None
            ),
            "last_error": state.last_error or None,
            "last_accepted": state.last_accepted,
            "last_skipped": state.last_skipped,
            "last_failed": state.last_failed,
            "enabled": bool(getattr(settings, "SUZ_RECONCILE_ENABLED", False)),
            "bitrix_base_url": getattr(settings, "BITRIX_REST_BASE_URL", "") or None,
            "changes_path": getattr(
                settings,
                "BITRIX_CHANGES_PATH",
                "/local/api/sufler/v1/changes",
            ),
        }
    )


@csrf_exempt
@require_http_methods(["POST"])
def knowledge_reconcile_run(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/knowledge/reconcile/run/ — trigger INT-09 polling now."""
    if ingest_mode() == "prod" and not getattr(
        settings, "SUZ_RECONCILE_ENABLED", False
    ):
        return JsonResponse(
            {"error": "disabled", "detail": "Set SUZ_RECONCILE_ENABLED=true"},
            status=403,
        )
    async_mode = (request.GET.get("async") or "").lower() in {"1", "true", "yes"}
    if async_mode:
        task = reconcile_suz_changes.delay()
        return JsonResponse(
            {
                "status": "queued",
                "task_id": task.id,
                "acceptance": ["INT-09"],
            },
            status=202,
        )
    result = run_reconciliation()
    status_code = 200 if result.get("status") == "ok" else 502
    return JsonResponse(result, status=status_code)
