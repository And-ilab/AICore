"""HTTP API for vendor pickup POST and operator call list."""

from __future__ import annotations

import json
import hmac
from typing import Any, Mapping

from django.conf import settings
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from auth.decorators import require_permissions
from auth.roles import PERM_SUFLER_CHAT, PERM_SUFLER_TELEPHONY
from integrations.oktell.call_hub import hub
from integrations.oktell.sip_pool import as_settings_snapshot
from integrations.oktell.webhook import OktellWebhookError, PickupEvent, parse_pickup_payload


def _json_body(request: HttpRequest) -> Mapping[str, Any]:
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise OktellWebhookError("body must be valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise OktellWebhookError("body must be a JSON object")
    return payload


def _webhook_authorized(request: HttpRequest) -> bool:
    secret = str(getattr(settings, "OKTELL_WEBHOOK_SECRET", "") or "")
    if not secret:
        return True
    offered = (
        request.headers.get("X-Oktell-Token")
        or request.headers.get("X-Sufler-Oktell-Token")
        or ""
    )
    return hmac.compare_digest(offered, secret)


@csrf_exempt
@require_http_methods(["POST"])
def oktell_call_started(request: HttpRequest) -> JsonResponse:
    """Vendor POST after the operator answers (CallerID / CalledID / Idchain)."""
    if not _webhook_authorized(request):
        return JsonResponse({"error": "auth"}, status=401)
    try:
        pickup = parse_pickup_payload(_json_body(request))
        live = hub.get("live")
        if live is not None and hub.is_listening("live"):
            noted = hub.attach_vendor_pickup("live", pickup)
            return JsonResponse(
                {"created": False, "call": (noted or live).as_dict()}
            )
        call, created = hub.start(pickup)
    except OktellWebhookError as exc:
        return JsonResponse({"error": "validation", "detail": str(exc)}, status=400)
    except RuntimeError as exc:
        return JsonResponse({"error": "misconfigured", "detail": str(exc)}, status=503)
    return JsonResponse({"created": created, "call": call.as_dict()}, status=201 if created else 200)


@csrf_exempt
@require_http_methods(["POST"])
def oktell_call_stopped(request: HttpRequest) -> JsonResponse:
    if not _webhook_authorized(request):
        return JsonResponse({"error": "auth"}, status=401)
    try:
        pickup = parse_pickup_payload(_json_body(request))
    except OktellWebhookError as exc:
        return JsonResponse({"error": "validation", "detail": str(exc)}, status=400)
    cleared = hub.clear_vendor_pickup(pickup.idchain)
    call = hub.stop(pickup.idchain)
    if call is None:
        live = hub.get("live")
        if cleared is not None and live is not None:
            return JsonResponse({"call": live.as_dict()})
        return JsonResponse({"error": "not_found", "Idchain": pickup.idchain}, status=404)
    return JsonResponse({"call": call.as_dict()})


@require_http_methods(["POST"])
@require_permissions(PERM_SUFLER_TELEPHONY, PERM_SUFLER_CHAT, require_all=False, api=True)
def oktell_listen_now(request: HttpRequest) -> JsonResponse:
    """Operator opened /sufler: keep one live barge on the inbound line."""
    line = str(getattr(settings, "OKTELL_SIP_LISTEN_LINE", "1001") or "1001")
    pickup = PickupEvent(
        caller_id="sufler",
        called_id=line,
        idchain="live",
        op_name="sufler",
        call_type="in",
    )
    slugs = _optional_kb_slugs(request)
    current = hub.get("live")
    if current is not None and hub.is_listening("live"):
        if slugs is not None:
            hub.set_kb_slugs("live", slugs)
            current = hub.get("live") or current
        return JsonResponse({"created": False, "call": current.as_dict()})
    try:
        call, created = hub.start(pickup)
    except RuntimeError as exc:
        return JsonResponse({"error": "misconfigured", "detail": str(exc)}, status=503)
    if slugs is not None:
        hub.set_kb_slugs("live", slugs)
        call = hub.get("live") or call
    return JsonResponse({"created": created, "call": call.as_dict()}, status=201 if created else 200)


def _optional_kb_slugs(request: HttpRequest) -> list[str] | None:
    """Slugs from the operator picker. Missing key means 'leave the previous choice'."""
    if not request.body:
        return None
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "kb_slugs" not in payload:
        return None
    raw = payload.get("kb_slugs")
    if not isinstance(raw, list):
        return None
    return [item.strip() for item in raw if isinstance(item, str) and item.strip()]


@require_GET
@require_permissions(PERM_SUFLER_TELEPHONY, PERM_SUFLER_CHAT, require_all=False, api=True)
def oktell_calls(request: HttpRequest) -> JsonResponse:
    calls = [
        call.as_dict()
        for call in hub.list_calls()
        if call.state != "stopped"
    ]
    calls.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
    return JsonResponse({"calls": calls, "listen": as_settings_snapshot()})


@csrf_exempt
@require_GET
def oktell_call_detail(request: HttpRequest, idchain: str) -> JsonResponse:
    """Public replay for TEST: window can load the last POST without a Django login."""
    call = hub.get(idchain)
    if call is None:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse({"call": call.as_dict()})
