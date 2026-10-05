"""CRUD and moderation for QU training examples (II.2.6 / FR-UND-09 / FR-UND-16)."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Mapping

from django.utils import timezone

from qu.models import QuReferenceExample, QuReplenishmentPolicy
from qu.tasks import qu_retrain

logger = logging.getLogger(__name__)

_WS_RE = re.compile(r"\s+")


class QuAdminError(ValueError):
    """Invalid QU training payload."""


def hash_question(question: str) -> str:
    normalized = _WS_RE.sub(" ", (question or "").casefold()).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_policy() -> QuReplenishmentPolicy:
    item = QuReplenishmentPolicy.objects.order_by("id").first()
    if item is None:
        item = QuReplenishmentPolicy.objects.create(
            mode=QuReplenishmentPolicy.MODE_AUTO_CONFIRM,
        )
    return item


def serialize_policy(item: QuReplenishmentPolicy | None = None) -> dict[str, Any]:
    policy = item or get_policy()
    return {
        "mode": policy.mode,
        "updated_at": policy.updated_at.isoformat() if policy.updated_at else "",
        "updated_by": policy.updated_by,
    }


def update_policy(payload: Mapping[str, Any], *, username: str) -> dict[str, Any]:
    mode = str(payload.get("mode") or "").strip()
    allowed = {
        QuReplenishmentPolicy.MODE_SUGGEST,
        QuReplenishmentPolicy.MODE_AUTO_CONFIRM,
        QuReplenishmentPolicy.MODE_AUTO,
    }
    if mode not in allowed:
        raise QuAdminError("mode must be suggest, auto_with_confirmation or auto")
    policy = get_policy()
    policy.mode = mode
    policy.updated_by = username
    policy.save(update_fields=["mode", "updated_by", "updated_at"])
    return serialize_policy(policy)


def serialize_example(item: QuReferenceExample) -> dict[str, Any]:
    return {
        "id": item.pk,
        "question": item.question,
        "article_id": item.article_id,
        "article_title": item.article_title,
        "intent_id": item.intent_id,
        "synonyms": item.synonyms,
        "locale": item.locale,
        "status": item.status,
        "is_active": item.is_active,
        "source": item.source,
        "source_feedback_id": item.source_feedback_id,
        "original_hint": item.original_hint,
        "relevance_percent": item.relevance_percent,
        "operator_name": item.operator_name,
        "channel": item.channel,
        "admin_comment": item.admin_comment,
        "created_by": item.created_by,
        "reviewed_by": item.reviewed_by,
        "reviewed_at": item.reviewed_at.isoformat() if item.reviewed_at else "",
        "created_at": item.created_at.isoformat() if item.created_at else "",
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
    }


def list_examples(*, status: str = "") -> dict[str, Any]:
    qs = QuReferenceExample.objects.all()
    if status:
        qs = qs.filter(status=status)
    items = [serialize_example(item) for item in qs[:400]]
    return {
        "items": items,
        "counts": {
            "active": QuReferenceExample.objects.filter(
                status=QuReferenceExample.STATUS_ACTIVE
            ).count(),
            "pending_review": QuReferenceExample.objects.filter(
                status=QuReferenceExample.STATUS_PENDING
            ).count(),
            "rejected": QuReferenceExample.objects.filter(
                status=QuReferenceExample.STATUS_REJECTED
            ).count(),
        },
    }


def list_bindable_documents() -> list[dict[str, Any]]:
    from hub.models import AssistantKnowledgeBaseDocument, KnowledgeBaseDocument

    rows: list[dict[str, Any]] = []
    for doc in KnowledgeBaseDocument.objects.select_related("knowledge_base").order_by(
        "filename"
    )[:400]:
        rows.append(
            {
                "article_id": doc.article_id,
                "title": doc.filename,
                "kb_name": doc.knowledge_base.name,
            }
        )
    for doc in AssistantKnowledgeBaseDocument.objects.select_related(
        "knowledge_base"
    ).order_by("filename")[:400]:
        rows.append(
            {
                "article_id": doc.article_id,
                "title": doc.filename,
                "kb_name": doc.knowledge_base.name,
            }
        )
    return rows


def _required_question(payload: Mapping[str, Any]) -> str:
    value = str(payload.get("question") or "").strip()
    if not value:
        raise QuAdminError("question is required")
    return value[:1000]


def _apply_payload(item: QuReferenceExample, payload: Mapping[str, Any]) -> None:
    if "question" in payload:
        item.question = _required_question(payload)
        item.question_hash = hash_question(item.question)
    if "intent_id" in payload:
        item.intent_id = str(payload.get("intent_id") or "").strip()[:128]
    if "article_id" in payload:
        raw = payload.get("article_id")
        if raw in (None, "", 0, "0"):
            item.article_id = None
        else:
            try:
                item.article_id = int(raw)
            except (TypeError, ValueError) as exc:
                raise QuAdminError("article_id must be an integer") from exc
    if "article_title" in payload:
        item.article_title = str(payload.get("article_title") or "").strip()[:255]
    if "synonyms" in payload:
        item.synonyms = str(payload.get("synonyms") or "").strip()
    if "locale" in payload:
        item.locale = str(payload.get("locale") or "ru").strip()[:8] or "ru"
    if "admin_comment" in payload:
        item.admin_comment = str(payload.get("admin_comment") or "").strip()


def create_example(payload: Mapping[str, Any], *, username: str) -> dict[str, Any]:
    question = _required_question(payload)
    digest = hash_question(question)
    existing = QuReferenceExample.objects.filter(question_hash=digest).exclude(
        status=QuReferenceExample.STATUS_REJECTED
    ).first()
    if existing:
        raise QuAdminError("duplicate question already exists in the training set")
    item = QuReferenceExample(
        question=question,
        question_hash=digest,
        status=QuReferenceExample.STATUS_ACTIVE,
        is_active=True,
        source=QuReferenceExample.SOURCE_MANUAL,
        created_by=username,
    )
    _apply_payload(item, payload)
    item.save()
    _enqueue_retrain("example.create")
    return serialize_example(item)


def update_example(
    example_id: int,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        item = QuReferenceExample.objects.get(pk=example_id)
    except QuReferenceExample.DoesNotExist as exc:
        raise QuAdminError("example not found") from exc
    _apply_payload(item, payload)
    if item.question_hash:
        duplicate = (
            QuReferenceExample.objects.filter(question_hash=item.question_hash)
            .exclude(pk=item.pk)
            .exclude(status=QuReferenceExample.STATUS_REJECTED)
            .first()
        )
        if duplicate:
            raise QuAdminError("duplicate question already exists in the training set")
    item.save()
    if item.status == QuReferenceExample.STATUS_ACTIVE:
        _enqueue_retrain("example.update")
    return serialize_example(item)


def delete_example(example_id: int) -> None:
    try:
        item = QuReferenceExample.objects.get(pk=example_id)
    except QuReferenceExample.DoesNotExist as exc:
        raise QuAdminError("example not found") from exc
    item.status = QuReferenceExample.STATUS_REJECTED
    item.is_active = False
    item.save(update_fields=["status", "is_active", "updated_at"])
    _enqueue_retrain("example.delete")


def review_example(
    example_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    try:
        item = QuReferenceExample.objects.get(pk=example_id)
    except QuReferenceExample.DoesNotExist as exc:
        raise QuAdminError("example not found") from exc
    action = str(payload.get("action") or "").strip()
    _apply_payload(item, payload)
    item.reviewed_by = username
    item.reviewed_at = timezone.now()
    if action == "approve":
        if not (item.intent_id or "").strip() and item.article_id is None:
            raise QuAdminError("intent_id or article_id is required to approve")
        item.status = QuReferenceExample.STATUS_ACTIVE
        item.is_active = True
    elif action == "reject":
        item.status = QuReferenceExample.STATUS_REJECTED
        item.is_active = False
    else:
        raise QuAdminError("action must be approve or reject")
    item.save()
    if action == "approve":
        _enqueue_retrain("example.approve")
    return serialize_example(item)


def enqueue_from_feedback(feedback: Any) -> QuReferenceExample | None:
    choice = getattr(feedback, "choice", "")
    if choice not in {"not_used", "partial"}:
        return None
    if get_policy().mode == QuReplenishmentPolicy.MODE_SUGGEST:
        return None
    question = str(getattr(feedback, "query", "") or "").strip()
    if not question:
        return None
    digest = hash_question(question)
    existing = QuReferenceExample.objects.filter(question_hash=digest).exclude(
        status=QuReferenceExample.STATUS_REJECTED
    ).first()
    if existing:
        return existing
    item = QuReferenceExample.objects.create(
        question=question[:1000],
        question_hash=digest,
        status=QuReferenceExample.STATUS_PENDING,
        is_active=False,
        source=QuReferenceExample.SOURCE_DIALOG,
        source_feedback_id=str(getattr(feedback, "id", "") or ""),
        original_hint=str(getattr(feedback, "hint_text", "") or ""),
        relevance_percent=getattr(feedback, "relevance_percent", None),
        operator_name=str(getattr(feedback, "operator_name", "") or "")[:160],
        channel=str(getattr(feedback, "source", "") or "chat")[:32],
        article_title=str(getattr(feedback, "citation_title", "") or "")[:255],
    )
    return item


def enqueue_from_asr_utterance(
    utterance: Any,
    *,
    session: Any = None,
) -> QuReferenceExample | None:
    question = str(getattr(utterance, "text", "") or "").strip()
    if not question or question in {"[нераспознано]", "[unrecognized]"}:
        return None
    digest = hash_question(question)
    existing = QuReferenceExample.objects.filter(question_hash=digest).exclude(
        status=QuReferenceExample.STATUS_REJECTED
    ).first()
    if existing:
        return existing
    session = session or getattr(utterance, "session", None)
    item = QuReferenceExample.objects.create(
        question=question[:1000],
        question_hash=digest,
        status=QuReferenceExample.STATUS_PENDING,
        is_active=False,
        source=QuReferenceExample.SOURCE_ASR,
        source_feedback_id=f"asr:{getattr(utterance, 'pk', '')}",
        operator_name=str(getattr(session, "operator_name", "") or "")[:160],
        channel=str(getattr(session, "channel", "") or "telephony")[:32],
    )
    return item


def _enqueue_retrain(trigger: str) -> None:
    try:
        qu_retrain.delay(
            kb_id="cc_production",
            reindex_job_id=f"qu-admin-{timezone.now().strftime('%Y%m%d%H%M%S')}",
            content_version=trigger,
            trigger=trigger,
        )
    except Exception:
        logger.exception("qu_retrain enqueue failed trigger=%s", trigger)
