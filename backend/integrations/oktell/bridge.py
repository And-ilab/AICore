"""Push ASR text into the sufler window WebSocket (call_id = Idchain)."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from integrations.oktell.caller_memory import remember_client_question
from integrations.oktell.profanity import mask_profanity
from orchestrator.sufler import suggest, telephony_turn_needs_hint

_SUGGEST_SECONDS = 20
_HINT_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="oktell-hint")
_SUGGEST_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="oktell-suggest")

logger = logging.getLogger(__name__)


def sufler_group(call_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in call_id)
    return f"sufler_call_{safe}"


def publish_to_call(call_id: str, payload: dict[str, Any]) -> None:
    try:
        from integrations.oktell.call_hub import hub

        hub.record_event(call_id, payload)
    except Exception:  # noqa: BLE001 — replay must not break live publish
        logger.debug("could not record oktell event for %s", call_id, exc_info=True)
    def _send() -> None:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            logger.warning("no channel layer; drop sufler event call_id=%s", call_id)
            return
        try:
            async_to_sync(channel_layer.group_send)(
                sufler_group(call_id),
                {"type": "sufler.event", "payload": payload},
            )
        except RuntimeError:
            logger.debug("skip live WS push for %s (async loop busy)", call_id)

    threading.Thread(target=_send, name=f"oktell-ws-{call_id[:8]}", daemon=True).start()


def publish_transcript(
    call_id: str,
    *,
    speaker: str,
    text: str,
    turn_id: str,
    is_final: bool = True,
) -> None:
    cleaned = text.strip()
    if not cleaned:
        return
    spoken = mask_profanity(cleaned)
    publish_to_call(
        call_id,
        {
            "type": "transcript",
            "speaker": speaker,
            "text": spoken,
            "is_final": is_final,
            "turn_id": turn_id,
        },
    )
    if not (is_final and speaker == "client"):
        return
    _remember_client_line(call_id, cleaned, spoken)
    _HINT_POOL.submit(_fill_hints, call_id, cleaned, turn_id)


def _remember_client_line(call_id: str, original: str, spoken: str) -> None:
    """Keep the question for the next call with this number. Hints still use the raw text."""
    if not telephony_turn_needs_hint(original):
        return
    try:
        from integrations.oktell.call_hub import hub

        call = hub.get(call_id)
    except Exception:
        logger.debug("caller memory skipped", exc_info=True)
        return
    if call is None:
        return
    remember_client_question(call.shown_caller_id(), spoken)


def _slugs_for_call(call_id: str) -> list[str] | None:
    """Operator picker, or every assistant base while the picker has not reported yet."""
    try:
        from integrations.oktell.call_hub import hub

        call = hub.get(call_id)
    except Exception:
        logger.debug("live kb slugs unavailable", exc_info=True)
        return None
    if call is None:
        return None
    if call.kb_slugs is not None:
        return list(call.kb_slugs)
    return _all_assistant_slugs()


def _all_assistant_slugs() -> list[str] | None:
    try:
        from hub.models import AssistantKnowledgeBase

        slugs = [
            slug
            for slug in AssistantKnowledgeBase.objects.values_list("slug", flat=True)
            if isinstance(slug, str) and slug.strip()
        ]
    except Exception:
        logger.debug("assistant kb list unavailable", exc_info=True)
        return None
    return slugs or None


def _live_hint_layout(hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Scenario on the left, one knowledge-base card on the right."""
    scenario = [item for item in hints if item.get("source_type") == "scenario"][:1]
    knowledge = [item for item in hints if item.get("source_type") != "scenario"][:1]
    laid: list[dict[str, Any]] = []
    for rank, item in enumerate([*scenario, *knowledge], start=1):
        copy = dict(item)
        copy["rank"] = rank
        laid.append(copy)
    return laid


def _fill_hints(call_id: str, text: str, turn_id: str) -> None:
    """Publish only the processed hint. A raw KB snippet is not shown first.

    DeepSeek runs on its own pool and does not pin later replicas.
    """
    slugs = _slugs_for_call(call_id)
    # The raw KB snippet is not shown. The first card is the processed answer.
    preview_published = False

    state = {"hints": False, "empty": False}
    lock = threading.Lock()

    def publish_result(result: dict[str, Any] | None) -> None:
        hints = _live_hint_layout(list((result or {}).get("hints") or []))
        with lock:
            if hints:
                state["hints"] = True
            elif state["hints"] or preview_published or state["empty"]:
                return
            else:
                state["empty"] = True
        if not hints or result is None:
            if result is None:
                _publish_empty_hints(call_id, turn_id)
            else:
                publish_to_call(
                    call_id,
                    {
                        "type": "hints",
                        "turn_id": turn_id,
                        "query": result.get("query") or text,
                        "hints": [],
                        "blocked_reason": result.get("blocked_reason"),
                        "scenario": result.get("scenario"),
                        "suggested_scenario": result.get("suggested_scenario"),
                    },
                )
            return
        publish_to_call(
            call_id,
            {
                "type": "hints",
                "turn_id": turn_id,
                "query": result.get("query") or text,
                "hints": hints[:5],
                "latency_ms": result.get("latency_ms"),
                "request_id": result.get("request_id"),
                "blocked_reason": result.get("blocked_reason"),
                "scenario": result.get("scenario"),
                "suggested_scenario": result.get("suggested_scenario"),
            },
        )

    def run_suggest() -> None:
        try:
            result = suggest(
                text,
                limit=5,
                session_id=call_id,
                channel="telephony",
                kb_slugs=slugs,
            )
        except Exception as exc:
            logger.warning("suggest failed for call %s: %s", call_id, exc)
            publish_result(None)
            return
        publish_result(result)

    _SUGGEST_POOL.submit(run_suggest)

    def on_timeout() -> None:
        with lock:
            if state["hints"] or preview_published or state["empty"]:
                return
            state["empty"] = True
        logger.warning("suggest timed out for call %s", call_id)
        _publish_empty_hints(call_id, turn_id)

    timer = threading.Timer(_SUGGEST_SECONDS, on_timeout)
    timer.daemon = True
    timer.start()


def _publish_empty_hints(call_id: str, turn_id: str) -> None:
    publish_to_call(
        call_id,
        {
            "type": "hints",
            "turn_id": turn_id,
            "hints": [],
            "blocked_reason": "sufler_unavailable",
        },
    )
