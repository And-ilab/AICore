from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass

from django.db import transaction

from core.embeddings import deterministic_embedding, embed_passage
from core.model_registry import ModelRegistry
from core.text_language import safe_ru_en_text
from ingest.models import CCProductionChunk, KnowledgeIngestEvent
from ingest.schema import SuzPayload, SuzPayloadError

# Re-export for tests/acceptance fixtures that import from ingest.pipeline.
__all__ = (
    "IngestResult",
    "checksum_for_text",
    "chunk_text",
    "deterministic_embedding",
    "ingest_payload",
    "normalize_text",
)

INDEX_NAME = "cc_production"
KC_SCOPES = frozenset({"kc_operator", "contact_center", "cc"})
WHITESPACE = re.compile(r"\s+")
HTML_TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class IngestResult:
    status: str
    outcome: str
    chunks_indexed: int = 0


def normalize_text(body_plain: str, body_html: str = "") -> str:
    source = body_plain or HTML_TAG.sub(" ", html.unescape(body_html))
    source = "".join(
        character if character.isprintable() else " "
        for character in source
    )
    return WHITESPACE.sub(" ", source).strip()


def checksum_for_text(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def chunk_text(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunk_size/overlap")
    tokens = text.split()
    if not tokens:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        chunks.append(" ".join(tokens[start : start + chunk_size]))
        if start + chunk_size >= len(tokens):
            break
        start += chunk_size - overlap
    return chunks


@transaction.atomic
def ingest_payload(payload: SuzPayload) -> IngestResult:
    event, created = KnowledgeIngestEvent.objects.get_or_create(
        event_id=payload.event_id,
        defaults={
            "article_id": payload.article_id,
            "version_id": payload.version_id,
            "event_type": payload.event_type,
            "checksum": payload.checksum,
            "outcome": "processing",
        },
    )
    if not created:
        return IngestResult(status="duplicate", outcome=event.outcome)

    if payload.event_type == "article.updated":
        event.outcome = "draft_ignored"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    if payload.event_type == "article.unpublished":
        CCProductionChunk.objects.filter(
            article_id=payload.article_id
        ).update(is_active=False)
        event.outcome = "soft_deleted"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    if payload.event_type == "article.deleted":
        CCProductionChunk.objects.filter(
            article_id=payload.article_id
        ).delete()
        event.outcome = "hard_deleted"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    if not KC_SCOPES.intersection(payload.visibility_scope):
        event.outcome = "scope_ignored"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    normalized = normalize_text(payload.body_plain, payload.body_html)
    if checksum_for_text(normalized) != payload.checksum:
        raise SuzPayloadError(["checksum"])
    if not safe_ru_en_text(payload.title) or not safe_ru_en_text(normalized):
        CCProductionChunk.objects.filter(article_id=payload.article_id).update(
            is_active=False
        )
        event.outcome = "language_quarantined"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    existing = CCProductionChunk.objects.filter(
        article_id=payload.article_id,
        checksum=payload.checksum,
        is_active=True,
    )
    if existing.exists():
        existing.update(
            version_id=payload.version_id,
            title=payload.title,
            permalink=payload.permalink,
            locale=payload.locale,
            visibility_scope=list(payload.visibility_scope),
        )
        event.outcome = "unchanged"
        event.save(update_fields=("outcome",))
        return IngestResult(status="accepted", outcome=event.outcome)

    registry = ModelRegistry.load()
    profile = registry.get_profile("kb_cc_production")
    chunks = chunk_text(
        normalized,
        chunk_size=profile.chunk_size_tokens,
        overlap=profile.chunk_overlap_tokens,
    )
    CCProductionChunk.objects.filter(article_id=payload.article_id).delete()
    CCProductionChunk.objects.bulk_create(
        [
            CCProductionChunk(
                article_id=payload.article_id,
                version_id=payload.version_id,
                chunk_index=index,
                title=payload.title,
                content=chunk,
                permalink=payload.permalink,
                locale=payload.locale,
                visibility_scope=list(payload.visibility_scope),
                checksum=payload.checksum,
                embedding_model=profile.embedding_model,
                embedding=embed_passage(chunk),
                is_active=True,
            )
            for index, chunk in enumerate(chunks)
        ]
    )
    event.outcome = "indexed"
    event.save(update_fields=("outcome",))
    return IngestResult(
        status="accepted",
        outcome=event.outcome,
        chunks_indexed=len(chunks),
    )
