"""HTTP API for contact-center sufler suggestions and internal KC test dialog."""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from auth.decorators import require_permissions
from auth.roles import (
    PERM_CC_TEST_DIALOG,
    PERM_SUFLER_CHAT,
    PERM_SUFLER_TELEPHONY,
)
from orchestrator.sufler import (
    SuflerOrchestratorError,
    enter_suggested_scenario,
    clear_active_scenario,
    pause_active_scenario,
    resume_active_scenario,
    suggest,
)
from orchestrator.test_dialog import run_test_prompt
from orchestrator.transcribe import TranscribeError, transcribe_wav

logger = logging.getLogger(__name__)


def _optional_string(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise SuflerOrchestratorError(f"{field} must be a string")
    return value


def _parse_suggest_body(
    body: bytes,
) -> tuple[str, int, str, str, list[str] | None, str, str, str]:
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise SuflerOrchestratorError(
            "Request body must be valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise SuflerOrchestratorError("Request body must be a JSON object")
    text = payload.get("text", payload.get("query"))
    if not isinstance(text, str) or not text.strip():
        raise SuflerOrchestratorError("text must be a non-empty string")
    limit: Any = payload.get("limit", 5)
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise SuflerOrchestratorError("limit must be an integer")
    history = payload.get("client_history", payload.get("history", ""))
    if history is None:
        history = ""
    if not isinstance(history, str):
        raise SuflerOrchestratorError("client_history must be a string")
    dialog_context = payload.get("dialog_context", "")
    if dialog_context is None:
        dialog_context = ""
    if not isinstance(dialog_context, str):
        raise SuflerOrchestratorError("dialog_context must be a string")
    kb_slugs: list[str] | None
    if "kb_slugs" not in payload:
        kb_slugs = None
    else:
        raw_slugs = payload.get("kb_slugs")
        if raw_slugs is None:
            kb_slugs = []
        elif not isinstance(raw_slugs, list):
            raise SuflerOrchestratorError("kb_slugs must be an array of strings")
        else:
            kb_slugs = []
            for index, slug in enumerate(raw_slugs):
                if not isinstance(slug, str) or not slug.strip():
                    raise SuflerOrchestratorError(
                        f"kb_slugs[{index}] must be a non-empty string"
                    )
                kb_slugs.append(slug.strip())
    channel = _optional_string(payload, "channel")
    mode = _optional_string(payload, "mode")
    session_id = _optional_string(payload, "session_id")
    return text, limit, history, dialog_context, kb_slugs, channel, mode, session_id


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_suggest(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/suggest — FR-CC-03 / FR-CC-14."""
    try:
        (
            text,
            limit,
            client_history,
            dialog_context,
            kb_slugs,
            channel,
            mode,
            session_id,
        ) = _parse_suggest_body(request.body)
        result = suggest(
            text,
            limit=limit,
            request_id=getattr(request, "audit_request_id", None),
            client_history=client_history,
            dialog_context=dialog_context,
            kb_slugs=kb_slugs,
            channel=channel,
            mode=mode,
            session_id=session_id,
        )
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    except ValueError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    except Exception:  # noqa: BLE001 — operator UI must never see a hard fail
        logger.exception("sufler_suggest_unhandled")
        return JsonResponse(
            {
                "query": "",
                "profile": "sufler_cc",
                "kb_id": "cc_production",
                "kb_slugs": [],
                "hints": [],
                "citations_enabled": True,
                "blocked_reason": "no_relevant_knowledge",
                "min_relevance": 0.2,
                "latency_ms": {"qu": 0.0, "rag": 0.0, "llm": 0.0, "total": 0.0},
                "request_id": "",
                "scenario": None,
                "suggested_scenario": None,
            }
        )
    response = JsonResponse(result)
    response["X-Request-ID"] = result.get("request_id") or ""
    return response


def _parse_scenario_session_body(body: bytes) -> tuple[str, str, str]:
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise SuflerOrchestratorError(
            "Request body must be valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise SuflerOrchestratorError("Request body must be a JSON object")
    session_id = _optional_string(payload, "session_id")
    if not session_id.strip():
        raise SuflerOrchestratorError("session_id must be a non-empty string")
    code = _optional_string(payload, "code")
    channel = _optional_string(payload, "channel")
    return session_id, code, channel


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_scenario_enter(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/scenario/enter — operator accepts a suggested scenario."""
    try:
        session_id, code, channel = _parse_scenario_session_body(request.body)
        if not code.strip():
            raise SuflerOrchestratorError("code must be a non-empty string")
        result = enter_suggested_scenario(
            code,
            session_id=session_id,
            channel=channel,
        )
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse(result)


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_scenario_exit(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/scenario/exit — operator leaves the active scenario."""
    try:
        session_id, _code, _channel = _parse_scenario_session_body(request.body)
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse(pause_active_scenario(session_id))


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_scenario_clear(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/scenario/clear — drop the session (new conversation)."""
    try:
        session_id, _code, _channel = _parse_scenario_session_body(request.body)
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse(clear_active_scenario(session_id))


def _parse_scenario_resume_body(body: bytes) -> tuple[str, str, str, str, str]:
    session_id, _code, channel = _parse_scenario_session_body(body)
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError:
        payload = {}
    mode = "checkpoint"
    node_id = ""
    dialog_context = ""
    if isinstance(payload, Mapping):
        mode = str(payload.get("mode") or "checkpoint").strip()
        node_id = str(payload.get("node_id") or "").strip()
        dialog_context = str(payload.get("dialog_context") or "")
    if mode not in {"start", "checkpoint", "step"}:
        raise SuflerOrchestratorError("mode must be start, checkpoint or step")
    return session_id, mode, channel, node_id, dialog_context


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_scenario_resume(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/scenario/resume — continue a paused scenario."""
    try:
        session_id, mode, channel, node_id, dialog_context = (
            _parse_scenario_resume_body(request.body)
        )
        result = resume_active_scenario(
            session_id,
            mode=mode,
            channel=channel,
            node_id=node_id,
            dialog_context=dialog_context,
        )
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse(result)


def _parse_test_dialog_body(body: bytes) -> tuple[str, str, bool]:
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise SuflerOrchestratorError(
            "Request body must be valid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise SuflerOrchestratorError("Request body must be a JSON object")
    text = payload.get("text", payload.get("query"))
    if not isinstance(text, str) or not text.strip():
        raise SuflerOrchestratorError("text must be a non-empty string")
    scenario_id = payload.get("scenario_id", "CC-SCR-008")
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise SuflerOrchestratorError("scenario_id must be a non-empty string")
    use_pipeline = payload.get("use_pipeline", True)
    if not isinstance(use_pipeline, bool):
        raise SuflerOrchestratorError("use_pipeline must be a boolean")
    return text, scenario_id, use_pipeline


@require_http_methods(["POST"])
@require_permissions(PERM_CC_TEST_DIALOG, api=True)
def sufler_test_dialog(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/test-dialog — II.3.5.5 / SUF-T-06."""
    try:
        text, scenario_id, use_pipeline = _parse_test_dialog_body(request.body)
        result = run_test_prompt(
            text,
            scenario_id=scenario_id,
            use_pipeline=use_pipeline,
            request_id=getattr(request, "audit_request_id", None),
        )
    except SuflerOrchestratorError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    response = JsonResponse(result)
    if result.get("request_id"):
        response["X-Request-ID"] = str(result["request_id"])
    return response


@require_http_methods(["POST"])
@require_permissions(
    PERM_SUFLER_TELEPHONY,
    PERM_SUFLER_CHAT,
    require_all=False,
    api=True,
)
def sufler_transcribe(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/sufler/transcribe — live dual-channel imitation STT."""
    speaker = str(request.POST.get("speaker") or "client")
    if speaker not in {"client", "operator"}:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["speaker must be client or operator"]},
            },
            status=400,
        )
    audio = request.FILES.get("audio")
    if audio is None:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": ["audio file is required"]},
            },
            status=400,
        )
    try:
        text = transcribe_wav(audio.read())
    except TranscribeError as exc:
        return JsonResponse(
            {
                "error": "validation_error",
                "details": {"request": [str(exc)]},
            },
            status=400,
        )
    return JsonResponse({"text": text, "speaker": speaker})
