"""Write one chat turn into the monitoring journal.

A failure here is logged and swallowed. The chat reply must not depend on it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from assistant.models import AssistantRequestEvent


logger = logging.getLogger("assistant.monitoring")

TEXT_LIMIT = 4000
TOPIC_EMPTY = "без источника"
_MS_LIMIT = 86_400_000.0


def derive_query_type(
    *,
    outcome: str,
    attachment_mode: bool,
    skill_used: bool,
    doc_count: int,
) -> str:
    if outcome == AssistantRequestEvent.OUTCOME_FILTER:
        return AssistantRequestEvent.QUERY_FILTER
    if outcome in (
        AssistantRequestEvent.OUTCOME_LLM_ERROR,
        AssistantRequestEvent.OUTCOME_ERROR,
    ):
        return AssistantRequestEvent.QUERY_LLM_ERROR
    if attachment_mode:
        return AssistantRequestEvent.QUERY_SUMMARY
    if outcome == AssistantRequestEvent.OUTCOME_NO_KB or doc_count <= 0:
        return AssistantRequestEvent.QUERY_NO_KB
    if skill_used:
        return AssistantRequestEvent.QUERY_SKILL
    return AssistantRequestEvent.QUERY_RAG


def context_threshold_percent() -> float | None:
    """Assistant profile floor, in the same 0–100 scale as stored relevance."""
    try:
        from hub.models import ModelRegistrySettings

        row = (
            ModelRegistrySettings.objects.filter(
                profile=ModelRegistrySettings.PROFILE_ASSISTANT,
            )
            .only("context_inclusion_threshold")
            .first()
        )
    except Exception:
        logger.warning("monitoring_threshold_unavailable")
        return None
    if row is None:
        return None
    try:
        return float(row.context_inclusion_threshold) * 100.0
    except (TypeError, ValueError):
        return None


def derive_error_reason(
    *,
    outcome: str,
    doc_count: int,
    top_relevance: float | None,
    attachment_mode: bool,
    threshold_percent: float | None,
) -> str:
    if outcome in (
        AssistantRequestEvent.OUTCOME_LLM_ERROR,
        AssistantRequestEvent.OUTCOME_ERROR,
    ):
        return AssistantRequestEvent.REASON_LLM_ERROR
    if outcome == AssistantRequestEvent.OUTCOME_FILTER:
        return AssistantRequestEvent.REASON_CONTENT_FILTER
    if outcome == AssistantRequestEvent.OUTCOME_NO_KB or (
        doc_count <= 0 and not attachment_mode
    ):
        return AssistantRequestEvent.REASON_NO_SOURCES
    if (
        top_relevance is not None
        and threshold_percent is not None
        and float(top_relevance) < threshold_percent
    ):
        return AssistantRequestEvent.REASON_LOW_RELEVANCE
    return AssistantRequestEvent.REASON_NONE


def _clip(value: str, limit: int = TEXT_LIMIT) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _ms(value: float | None) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or number > _MS_LIMIT:
        return None
    return round(number, 1)


def record_chat_event(
    *,
    request_id: str,
    message_id: str = "",
    session_id: str = "",
    username: str = "",
    department: str = "",
    question_text: str = "",
    answer_text: str = "",
    outcome: str | None = None,
    total_ms: float | None = None,
    ttft_ms: float | None = None,
    llm_ms: float | None = None,
    top_relevance: float | None = None,
    doc_count: int = 0,
    kb_slugs: list[str] | None = None,
    source_title: str = "",
    attachment_mode: bool = False,
    skill_used: bool = False,
) -> None:
    """Insert or refresh one event. Never raises into the chat stream."""
    try:
        _write_event(
            request_id=request_id,
            message_id=message_id,
            session_id=session_id,
            username=username,
            department=department,
            question_text=question_text,
            answer_text=answer_text,
            outcome=outcome,
            total_ms=total_ms,
            ttft_ms=ttft_ms,
            llm_ms=llm_ms,
            top_relevance=top_relevance,
            doc_count=doc_count,
            kb_slugs=kb_slugs,
            source_title=source_title,
            attachment_mode=attachment_mode,
            skill_used=skill_used,
        )
    except Exception as exc:
        # Class name only: exception text can echo SQL or the user question.
        logger.warning(
            "metric_write_failed request_id=%s error_type=%s",
            (request_id or "-")[:64],
            type(exc).__name__,
        )


def _write_event(
    *,
    request_id: str,
    message_id: str,
    session_id: str,
    username: str,
    department: str,
    question_text: str,
    answer_text: str,
    outcome: str | None,
    total_ms: float | None,
    ttft_ms: float | None,
    llm_ms: float | None,
    top_relevance: float | None,
    doc_count: int,
    kb_slugs: list[str] | None,
    source_title: str,
    attachment_mode: bool,
    skill_used: bool,
) -> None:
    key = (request_id or "").strip()[:64] or uuid.uuid4().hex
    stored_outcome = outcome or AssistantRequestEvent.OUTCOME_ERROR
    allowed = {item[0] for item in AssistantRequestEvent.OUTCOME_CHOICES}
    if stored_outcome not in allowed:
        stored_outcome = AssistantRequestEvent.OUTCOME_ERROR
    relevance = None
    if isinstance(top_relevance, (int, float)) and not isinstance(top_relevance, bool):
        relevance = float(top_relevance)
    title = _clip(source_title, 255)
    slugs = [
        str(slug).strip()[:64]
        for slug in (kb_slugs or [])
        if str(slug).strip()
    ][:20]
    threshold = context_threshold_percent()
    defaults: dict[str, Any] = {
        "message_id": _clip(message_id, 64),
        "session_id": _clip(session_id, 64),
        "username": _clip(username, 150),
        "department": _clip(department, 128),
        "query_type": derive_query_type(
            outcome=stored_outcome,
            attachment_mode=attachment_mode,
            skill_used=skill_used,
            doc_count=doc_count,
        ),
        "topic": title or TOPIC_EMPTY,
        "outcome": stored_outcome,
        "error_reason": derive_error_reason(
            outcome=stored_outcome,
            doc_count=doc_count,
            top_relevance=relevance,
            attachment_mode=attachment_mode,
            threshold_percent=threshold,
        ),
        "total_ms": _ms(total_ms),
        "ttft_ms": _ms(ttft_ms),
        "llm_ms": _ms(llm_ms),
        "top_relevance": relevance,
        "doc_count": max(0, int(doc_count)),
        "kb_slugs": slugs,
        "source_title": title,
        "question_text": _clip(question_text),
        "answer_text": _clip(answer_text),
    }
    try:
        with transaction.atomic():
            event, created = AssistantRequestEvent.objects.get_or_create(
                request_id=key,
                defaults=defaults,
            )
            if created:
                return
            for field, value in defaults.items():
                setattr(event, field, value)
            event.save(update_fields=[*defaults.keys()])
    except IntegrityError:
        AssistantRequestEvent.objects.filter(request_id=key).update(**defaults)


def mark_hallucination(
    event: AssistantRequestEvent,
    *,
    marked: bool,
    user_id: int | None,
) -> AssistantRequestEvent:
    event.hallucination_marked = marked
    event.hallucination_marked_by_id = user_id if marked else None
    event.hallucination_marked_at = timezone.now() if marked else None
    event.save(
        update_fields=[
            "hallucination_marked",
            "hallucination_marked_by_id",
            "hallucination_marked_at",
        ]
    )
    return event
