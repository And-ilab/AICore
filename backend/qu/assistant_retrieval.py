"""RAG retrieval over ``assistant_production`` (+ optional ``cc_production`` / SUZ)."""

from __future__ import annotations

import math
import re
from typing import Any, Sequence
from urllib.parse import unquote, urlparse

from django.db import connection
from django.db.models import Q, QuerySet
from pgvector.django import CosineDistance

from core.embeddings import embed_query_with_backend
from hub.kb_admin import ARTICLE_ID_BASE, SUZ_KB_SLUG
from hub.model_registry_store import get_model_settings
from hub.models import ContactCenterKnowledgeBase, KnowledgeBaseDocument
from ingest.models import AssistantProductionChunk, CCProductionChunk
from qu.models import QuReferenceExample
from qu.service import (
    EXAMPLE_MATCH_FLOOR,
    _PHONE_FACT_RE,
    _PUBLIC_CONTACT_QUERY_RE,
    _distinctive_terms,
    _lexical_score,
    _lookup_hit_count,
    _lookup_terms,
    boost_chunks_with_examples,
    expand_user_query,
    extractive_answer,
    focused_snippet,
    matching_training_examples,
    topical_relevance_score,
    training_example_score,
)


DEFAULT_LIMIT = 5
MAX_LIMIT = 8
# Keep a short preview for UI citations; LLM must see the full chunk text.
SNIPPET_PREVIEW_CHARS = 1200
# Header-only first chunk often drops the answering clause («до 23 лет»).
MAX_CHUNKS_PER_ARTICLE = 3
_PATH_TOKEN_RE = re.compile(r"[a-zа-яё0-9]{3,}", re.IGNORECASE)
_HOME_PATHS = frozenset({"", "ru", "en", "by", "index", "index.html", "home"})
_URL_ALIASES = (
    ("контакт", ("contact", "kontact", "kontakty", "hotline")),
    ("телефон", ("phone", "tel", "hotline", "call")),
    ("адрес", ("address", "office", "ofis")),
    ("офис", ("office", "ofis", "head")),
)
_HR_CONTACT_CENTER_RE = re.compile(
    r"премирован|работник\w*\s+контакт|контакт-центр\w*\s+работ|"
    r"оплат\w+\s+труд\w*\s+контакт|дистанционн\w+\s+взаимодейств",
    re.IGNORECASE,
)
_CONTACT_LABEL_RE = re.compile(
    r"справочн\w*\s+номер|единый справочн|обратная связь|"
    r"юридическ\w+\s+адрес|головн\w+\s+офис",
    re.IGNORECASE,
)


def _joined_article_content(article_id: int) -> str:
    """All chunks of one file, in order — preview must see the answering clause."""
    parts = list(
        CCProductionChunk.objects.filter(is_active=True, article_id=article_id)
        .order_by("chunk_index")
        .values_list("content", flat=True)
    )
    if not parts:
        parts = list(
            AssistantProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
            )
            .order_by("chunk_index")
            .values_list("content", flat=True)
        )
    return "\n".join(part for part in parts if part)


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _normalize_slugs(kb_slugs: Sequence[str] | None) -> list[str]:
    return [
        slug.strip()
        for slug in (kb_slugs or [])
        if isinstance(slug, str) and slug.strip()
    ]


def _split_slugs(slugs: Sequence[str]) -> tuple[list[str], bool, list[int]]:
    """Return (assistant_slugs, include_suz, cc_manual_article_ids)."""
    from hub.models import AssistantKnowledgeBase

    assistant_slugs: list[str] = []
    include_suz = False
    cc_article_ids: list[int] = []
    for slug in slugs:
        if slug == SUZ_KB_SLUG:
            include_suz = True
            continue
        if slug.startswith("assistant:"):
            pk = slug.split(":", 1)[1]
            kb = AssistantKnowledgeBase.objects.filter(pk=pk).only("slug").first()
            if kb is not None:
                assistant_slugs.append(kb.slug)
            continue
        if slug.startswith("cc:"):
            pk = slug.split(":", 1)[1]
            kb = (
                ContactCenterKnowledgeBase.objects.filter(pk=pk)
                .only("id", "source", "slug")
                .first()
            )
            if kb is None:
                continue
            if kb.source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX or kb.slug == SUZ_KB_SLUG:
                include_suz = True
            else:
                ids = list(
                    KnowledgeBaseDocument.objects.filter(knowledge_base_id=kb.pk).values_list(
                        "article_id",
                        flat=True,
                    )
                )
                cc_article_ids.extend(int(value) for value in ids)
            continue
        if slug.startswith("assistant_"):
            assistant_slugs.append(slug)
            continue
        kb = (
            ContactCenterKnowledgeBase.objects.filter(slug=slug)
            .only("id", "source", "slug")
            .first()
        )
        if kb is None:
            # Unknown slug: keep as assistant filter for backward compatibility.
            assistant_slugs.append(slug)
            continue
        if kb.source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX:
            include_suz = True
            continue
        ids = list(
            KnowledgeBaseDocument.objects.filter(knowledge_base_id=kb.pk).values_list(
                "article_id",
                flat=True,
            )
        )
        cc_article_ids.extend(int(value) for value in ids)

    return assistant_slugs, include_suz, cc_article_ids


def _kb_display_names(slugs: Sequence[str]) -> dict[str, str]:
    """Human KB titles for topical ranking (file name alone is often Latin)."""
    from hub.models import AssistantKnowledgeBase

    names: dict[str, str] = {}
    wanted = [slug for slug in slugs if slug]
    if not wanted:
        return names
    for slug, name in AssistantKnowledgeBase.objects.filter(slug__in=wanted).values_list(
        "slug", "name"
    ):
        names[str(slug)] = str(name or "")
    for slug, name in ContactCenterKnowledgeBase.objects.filter(slug__in=wanted).values_list(
        "slug", "name"
    ):
        names.setdefault(str(slug), str(name or ""))
    return names


def _rerank_scored_chunks(
    query: str,
    scored_chunks: list[tuple[float, Any, str]],
) -> list[tuple[float, Any, str]]:
    """Down-rank long off-topic dumps; boost the file that actually answers."""
    if not scored_chunks:
        return scored_chunks
    if len(_distinctive_terms(query)) < 2:
        return scored_chunks
    labels = _kb_display_names({slug for _score, _chunk, slug in scored_chunks})
    rescored: list[tuple[float, Any, str]] = []
    for score, chunk, slug in scored_chunks:
        topical = topical_relevance_score(
            query,
            chunk.title or "",
            chunk.content or "",
            extra=labels.get(slug, ""),
        )
        original = float(score)
        mixed = min(1.0, 0.74 * topical + 0.26 * original)
        # Keep ANN/lexical only when the passage is clearly on-topic.
        # Otherwise a long credit dump with 80% stem-recall stays on top.
        if topical >= 0.55:
            blended = max(original, mixed)
        elif topical >= 0.42:
            blended = mixed
        else:
            blended = min(original, mixed)
        blended = max(
            0.0,
            min(
                1.0,
                blended
                + contact_fact_signal(
                    query, chunk.title or "", chunk.content or ""
                ),
            ),
        )
        rescored.append((blended, chunk, slug))
    rescored.sort(
        key=lambda item: (
            -item[0],
            item[2],
            item[1].article_id,
            item[1].chunk_index,
        )
    )
    return rescored


_CASE_MARKERS = (
    "оздоровлен",
    "брак",
    "рожден",
    "усыновл",
    "смерт",
    "пенси",
    "увечь",
    "найм",
    "отпуск",
    "пособ",
    "заявлен",
    "документ",
)


def _content_only_score(query: str, content: str) -> float:
    """Ignore the file name so the cover page does not beat the answering chapter."""
    base = topical_relevance_score(query, "", content or "")
    blob = (content or "").casefold()
    diversity = sum(1 for marker in _CASE_MARKERS if marker in blob)
    hits = _lookup_hit_count(query, content)
    return base + min(0.18, 0.03 * diversity) + min(0.45, 0.16 * hits)


def _article_chunks_by_content(
    query: str,
    slug: str,
    article_id: int,
    quota: int,
    fallback: list[tuple[float, Any, str]],
) -> list[tuple[float, Any, str]]:
    """After the right file is chosen, pick passages that answer the question."""
    assistant = list(
        AssistantProductionChunk.objects.filter(
            is_active=True,
            article_id=article_id,
            kb_slug=slug,
        ).order_by("chunk_index")
    )
    if not assistant:
        assistant = list(
            CCProductionChunk.objects.filter(
                is_active=True,
                article_id=article_id,
            ).order_by("chunk_index")
        )
    if not assistant:
        return fallback[:quota]
    scored = [
        (_content_only_score(query, chunk.content or ""), chunk, slug)
        for chunk in assistant
    ]
    scored.sort(key=lambda row: (-row[0], row[1].chunk_index))
    if scored[0][0] < 0.12:
        return fallback[:quota]
    return scored[:quota]


def _select_ranked_chunks(
    scored_chunks: list[tuple[float, Any, str]],
    *,
    limit: int,
    query: str = "",
) -> list[tuple[float, Any, str]]:
    """Best article first (answering chunks), then one chunk from each next file."""
    by_article: dict[tuple[str, int], list[tuple[float, Any, str]]] = {}
    for item in scored_chunks:
        _score, chunk, slug = item
        key = (slug, int(chunk.article_id))
        by_article.setdefault(key, []).append(item)
    for items in by_article.values():
        items.sort(key=lambda row: (-row[0], row[1].chunk_index))
    def _article_key(key: tuple[str, int]) -> tuple[float, float, float, str, int]:
        hits = 0
        topical = 0.0
        score = 0.0
        for item_score, chunk, _slug in by_article[key]:
            score = max(score, float(item_score))
            text = f"{chunk.title or ''}\n{chunk.content or ''}"
            item_hits = _lookup_hit_count(query, text) if query.strip() else 0
            item_topical = (
                topical_relevance_score(query, chunk.title or "", chunk.content or "")
                if query.strip()
                else 0.0
            )
            if item_hits > hits or (item_hits == hits and item_topical > topical):
                hits = item_hits
                topical = item_topical
        return (-float(hits), -topical, -score, key[0], key[1])

    article_order = sorted(by_article, key=_article_key)
    picked: list[tuple[float, Any, str]] = []
    for index, key in enumerate(article_order):
        quota = MAX_CHUNKS_PER_ARTICLE if index == 0 else 1
        chosen = by_article[key]
        if index == 0 and query.strip() and quota > 1:
            chosen = _article_chunks_by_content(
                query, key[0], key[1], quota, by_article[key]
            )
        for item in chosen[:quota]:
            picked.append(item)
            if len(picked) >= limit:
                return picked
    return picked


def _score_queryset(
    chunk_query: QuerySet,
    query_embedding: list[float],
    *,
    limit: int,
) -> list[tuple[float, Any]]:
    if connection.vendor == "postgresql":
        chunks = list(
            chunk_query.annotate(
                distance=CosineDistance("embedding", query_embedding)
            ).order_by("distance", "article_id")[: limit * 20]
        )
        return [
            (max(0.0, min(1.0, 1.0 - float(chunk.distance))), chunk)
            for chunk in chunks
        ]
    chunks = list(chunk_query)
    return [
        (
            _cosine_similarity(query_embedding, list(chunk.embedding)),
            chunk,
        )
        for chunk in chunks
    ]


def _permalink_text(permalink: str) -> str:
    raw = (permalink or "").strip()
    if not raw.startswith(("http://", "https://")):
        return ""
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    path = unquote(parsed.path or "").casefold()
    return f"{parsed.netloc} {path.replace('/', ' ').replace('-', ' ').replace('_', ' ')}"


def contact_fact_signal(query: str, title: str, content: str) -> float:
    """Lift a page that actually lists phones; drop HR texts about the call centre."""
    if not _PUBLIC_CONTACT_QUERY_RE.search(query or ""):
        return 0.0
    blob = f"{title or ''}\n{content or ''}"
    if _HR_CONTACT_CENTER_RE.search(blob) and not _PHONE_FACT_RE.search(blob):
        return -0.32
    boost = 0.0
    if _PHONE_FACT_RE.search(blob):
        boost += 0.34
    if "147" in blob:
        boost += 0.10
    if _CONTACT_LABEL_RE.search(blob):
        boost += 0.10
    return min(0.45, boost)


def permalink_signal(query: str, permalink: str) -> float:
    """Prefer the answering page URL over a site homepage with the same footer."""
    raw = (permalink or "").strip()
    if not raw.startswith(("http://", "https://")):
        return 0.0
    try:
        parsed = urlparse(raw)
    except ValueError:
        return 0.0
    parts = [part for part in unquote(parsed.path or "").casefold().split("/") if part]
    path_text = " ".join(parts).replace("-", " ").replace("_", " ")
    query_tokens = {
        token.casefold()
        for token in _PATH_TOKEN_RE.findall(query)
        if len(token) >= 4
    }
    hits = 0
    for token in query_tokens:
        if token in path_text:
            hits += 1
        for russian, aliases in _URL_ALIASES:
            if token.startswith(russian) and any(alias in path_text for alias in aliases):
                hits += 1
                break
    boost = min(0.12, 0.05 * hits)
    if not parts or (len(parts) == 1 and parts[0] in _HOME_PATHS):
        if query_tokens:
            boost -= 0.05
    return boost


def _chunk_lexical(query: str, chunk: Any) -> float:
    extra = _permalink_text(str(getattr(chunk, "permalink", "") or ""))
    return _lexical_score(query, chunk.title, f"{chunk.content}\n{extra}")


def _with_permalink_signal(
    scored: list[tuple[float, Any]],
    query: str,
) -> list[tuple[float, Any]]:
    adjusted = [
        (
            max(
                0.0,
                min(
                    1.0,
                    float(score)
                    + permalink_signal(query, str(getattr(chunk, "permalink", "") or "")),
                ),
            ),
            chunk,
        )
        for score, chunk in scored
    ]
    adjusted.sort(key=lambda item: (-item[0], item[1].article_id, item[1].chunk_index))
    return adjusted


def _rank_chunks_hybrid(
    chunk_query: QuerySet,
    query_text: str,
    query_embedding: list[float],
    *,
    backend: str,
    limit: int,
) -> list[tuple[float, Any]]:
    """Blend vector similarity with keyword overlap so short RU questions still hit."""
    if backend in {"http-fallback", "lexical"}:
        scored = []
        for chunk in chunk_query:
            score = _chunk_lexical(query_text, chunk)
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda item: (-item[0], item[1].article_id))
        return _with_permalink_signal(scored, query_text)[: limit * 20]

    vector_scored = _score_queryset(
        chunk_query, query_embedding, limit=limit
    )
    combined: dict[tuple[int, int], tuple[float, Any]] = {}
    for vector_score, chunk in vector_scored:
        lexical = _chunk_lexical(query_text, chunk)
        combined[(int(chunk.article_id), int(chunk.chunk_index))] = (
            max(float(vector_score), lexical),
            chunk,
        )
    # Always keep lexical hits: a later-indexed file can lose the ANN window
    # when stub/e5 cosine is high on a long unrelated dump.
    for chunk in list(chunk_query[:2500]):
        key = (int(chunk.article_id), int(chunk.chunk_index))
        lexical = _chunk_lexical(query_text, chunk)
        if lexical <= 0.2:
            continue
        previous = combined.get(key)
        if previous is None or lexical > previous[0]:
            combined[key] = (lexical, chunk)
    _merge_lookup_hits(chunk_query, query_text, combined)
    ranked = _with_permalink_signal(
        list(combined.values()),
        query_text,
    )
    head = ranked[: max(limit * 40, 200)]
    return _keep_lookup_hits(query_text, ranked, head)


def _merge_lookup_hits(
    chunk_query: QuerySet,
    query_text: str,
    combined: dict[tuple[int, int], tuple[float, Any]],
) -> None:
    """Pull the clause that contains the question words, even past the ANN window."""
    terms = _lookup_terms(query_text)
    if not terms:
        return
    # One query per stem so a common word («мате») cannot crowd out «стаж» or «убыт».
    for term in terms:
        for chunk in chunk_query.filter(content__icontains=term)[:40]:
            if _lookup_hit_count(query_text, chunk.content or "") <= 0:
                continue
            key = (int(chunk.article_id), int(chunk.chunk_index))
            score = topical_relevance_score(
                query_text,
                chunk.title or "",
                chunk.content or "",
            )
            previous = combined.get(key)
            if previous is None or score > previous[0]:
                combined[key] = (score, chunk)


def _keep_lookup_hits(
    query_text: str,
    ranked: list[tuple[float, Any]],
    head: list[tuple[float, Any]],
) -> list[tuple[float, Any]]:
    """Do not drop the answering clause just because vector score filled the window."""
    seen = {
        (int(chunk.article_id), int(chunk.chunk_index)) for _score, chunk in head
    }
    extras: list[tuple[int, float, Any]] = []
    for score, chunk in ranked:
        key = (int(chunk.article_id), int(chunk.chunk_index))
        if key in seen:
            continue
        hits = _lookup_hit_count(query_text, f"{chunk.title or ''}\n{chunk.content or ''}")
        if hits <= 0:
            continue
        extras.append((hits, float(score), chunk))
        seen.add(key)
    extras.sort(key=lambda item: (-item[0], -item[1]))
    head.extend((score, chunk) for _hits, score, chunk in extras[:30])
    return head


def _document_from_chunk(
    *,
    rank: int,
    score: float,
    chunk: Any,
    kb_slug: str,
    threshold: float,
    query: str,
    content: str | None = None,
) -> dict[str, Any]:
    text = content if content is not None else (chunk.content or "")
    return {
        "rank": rank,
        "kb_slug": kb_slug,
        "article_id": chunk.article_id,
        "chunk_index": chunk.chunk_index,
        "title": chunk.title,
        "permalink": chunk.permalink,
        "content": text,
        "snippet": focused_snippet(text, query, SNIPPET_PREVIEW_CHARS),
        "relevance_score": round(score, 4),
        "relevance_percent": round(score * 100),
        "meets_min_relevance": score >= threshold,
    }


def preview_assistant_query(
    query: str,
    *,
    kb_slugs: Sequence[str] | None = None,
    limit: int = DEFAULT_LIMIT,
    search_all: bool = False,
    group_articles: bool = False,
) -> dict[str, Any]:
    """Rank active chunks; assistant_* plus optional SUZ/CC when selected."""
    normalized_query = expand_user_query(query.strip())
    if not normalized_query:
        raise ValueError("query must be a non-empty string")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

    slugs = _normalize_slugs(kb_slugs)
    if search_all:
        assistant_slugs: list[str] = []
        include_suz = True
        cc_article_ids: list[int] = []
        search_assistant = True
        search_cc = True
    else:
        assistant_slugs, include_suz, cc_article_ids = _split_slugs(slugs)
        # Empty selection → previous behavior: all assistant_* only.
        search_assistant = not slugs or bool(assistant_slugs)
        search_cc = bool(include_suz or cc_article_ids)

    query_embedding, backend = embed_query_with_backend(normalized_query)
    scored_chunks: list[tuple[float, Any, str]] = []
    article_slug_map: dict[int, str] = {}

    if search_assistant:
        chunk_query = AssistantProductionChunk.objects.filter(is_active=True).only(
            "kb_slug",
            "article_id",
            "chunk_index",
            "title",
            "content",
            "permalink",
            "embedding",
        )
        if slugs and not search_all:
            chunk_query = chunk_query.filter(kb_slug__in=assistant_slugs or ["__none__"])
        for score, chunk in _rank_chunks_hybrid(
            chunk_query,
            normalized_query,
            query_embedding,
            backend=backend,
            limit=limit,
        ):
            scored_chunks.append((score, chunk, chunk.kb_slug))

    if search_cc:
        cc_query = CCProductionChunk.objects.filter(is_active=True).only(
            "article_id",
            "chunk_index",
            "title",
            "content",
            "permalink",
            "embedding",
        )
        if not search_all:
            if include_suz and cc_article_ids:
                from django.db.models import Q

                cc_query = cc_query.filter(
                    Q(article_id__lt=ARTICLE_ID_BASE) | Q(article_id__in=cc_article_ids)
                )
            elif include_suz:
                cc_query = cc_query.filter(article_id__lt=ARTICLE_ID_BASE)
            else:
                cc_query = cc_query.filter(article_id__in=cc_article_ids or [-1])
        article_slug_map = {
            int(article_id): slug
            for article_id, slug in KnowledgeBaseDocument.objects.filter(
                **({} if search_all else {"article_id__in": cc_article_ids or []})
            ).values_list("article_id", "knowledge_base__slug")
        }
        for score, chunk in _rank_chunks_hybrid(
            cc_query,
            normalized_query,
            query_embedding,
            backend=backend,
            limit=limit,
        ):
            article_id = int(chunk.article_id)
            kb_slug = (
                SUZ_KB_SLUG
                if article_id < ARTICLE_ID_BASE
                else article_slug_map.get(article_id, "cc_manual")
            )
            scored_chunks.append((score, chunk, kb_slug))

    single_scope = (
        bool(slugs)
        and not search_all
        and len(assistant_slugs) <= 1
        and not include_suz
        and not cc_article_ids
    )
    if not single_scope:
        scored_chunks = _rerank_scored_chunks(normalized_query, scored_chunks)
    matches = matching_training_examples(normalized_query)
    pin_ids = [int(matches[0][1].article_id)] if matches else []
    extra_pairs: list[tuple[Any, str]] = []
    if pin_ids and search_cc:
        cc_extra = CCProductionChunk.objects.filter(
            is_active=True,
            article_id__in=pin_ids,
        )
        if not search_all:
            if include_suz and cc_article_ids:
                from django.db.models import Q

                cc_extra = cc_extra.filter(
                    Q(article_id__lt=ARTICLE_ID_BASE) | Q(article_id__in=cc_article_ids)
                )
            elif include_suz:
                cc_extra = cc_extra.filter(article_id__lt=ARTICLE_ID_BASE)
            elif cc_article_ids:
                cc_extra = cc_extra.filter(article_id__in=cc_article_ids)
        for chunk in cc_extra:
            article_id = int(chunk.article_id)
            extra_pairs.append(
                (
                    chunk,
                    SUZ_KB_SLUG
                    if article_id < ARTICLE_ID_BASE
                    else article_slug_map.get(article_id, "cc_manual"),
                )
            )
    if pin_ids and search_assistant:
        assistant_extra = AssistantProductionChunk.objects.filter(
            is_active=True,
            article_id__in=pin_ids,
        )
        if slugs and not search_all:
            assistant_extra = assistant_extra.filter(
                kb_slug__in=assistant_slugs or ["__none__"]
            )
        for chunk in assistant_extra:
            extra_pairs.append((chunk, chunk.kb_slug))
    if pin_ids:
        boosted = boost_chunks_with_examples(
            [(score, chunk) for score, chunk, _kb in scored_chunks],
            normalized_query,
            [chunk for chunk, _kb in extra_pairs],
        )
        slug_by_key = {
            (int(chunk.article_id), int(chunk.chunk_index)): kb_slug
            for _score, chunk, kb_slug in scored_chunks
        }
        for chunk, kb_slug in extra_pairs:
            slug_by_key.setdefault(
                (int(chunk.article_id), int(chunk.chunk_index)),
                kb_slug,
            )
        scored_chunks = [
            (
                score,
                chunk,
                slug_by_key.get(
                    (int(chunk.article_id), int(getattr(chunk, "chunk_index", 0))),
                    "cc_manual",
                ),
            )
            for score, chunk in boosted
        ]

    threshold = get_model_settings(
        "assistant_bank"
    ).context_inclusion_threshold
    if group_articles:
        grouped: dict[tuple[str, int], list[tuple[float, Any, str]]] = {}
        for score, chunk, kb_slug in scored_chunks:
            grouped.setdefault((kb_slug, int(chunk.article_id)), []).append(
                (score, chunk, kb_slug)
            )
        ranked_articles: list[tuple[float, Any, str, str]] = []
        for items in grouped.values():
            items.sort(key=lambda item: item[1].chunk_index)
            score = max(item[0] for item in items)
            content = "\n".join(item[1].content or "" for item in items)
            best = max(
                items,
                key=lambda item: (
                    _lexical_score(
                        normalized_query,
                        item[1].title,
                        item[1].content,
                    ),
                    item[0],
                ),
            )
            ranked_articles.append((score, best[1], best[2], content))
        ranked_articles.sort(
            key=lambda item: (-item[0], item[2], item[1].article_id)
        )
        documents = [
            _document_from_chunk(
                rank=rank,
                score=score,
                chunk=chunk,
                kb_slug=kb_slug,
                threshold=threshold,
                query=normalized_query,
                content=content,
            )
            for rank, (score, chunk, kb_slug, content) in enumerate(
                ranked_articles[:limit], start=1
            )
        ]
    else:
        ranked = _select_ranked_chunks(
            scored_chunks, limit=limit, query=normalized_query
        )
        documents = [
            _document_from_chunk(
                rank=rank,
                score=score,
                chunk=chunk,
                kb_slug=kb_slug,
                threshold=threshold,
                query=normalized_query,
            )
            for rank, (score, chunk, kb_slug) in enumerate(ranked, start=1)
        ]

    return {
        "query": normalized_query,
        "kb_id": "assistant_production+cc_production",
        "kb_slugs": slugs,
        "min_relevance": threshold,
        "min_relevance_percent": round(threshold * 100),
        "documents": documents,
    }


def preview_admin_query(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Hub QU preview: every indexed file, with training pins and an extractive hint."""
    result = preview_assistant_query(
        query,
        search_all=True,
        group_articles=True,
        limit=limit,
    )
    normalized_query = str(result.get("query") or query).strip()
    examples = list(QuReferenceExample.objects.filter(is_active=True))
    examples_by_article: dict[int, list[QuReferenceExample]] = {}
    for example in examples:
        if example.article_id is None:
            continue
        examples_by_article.setdefault(int(example.article_id), []).append(example)

    documents = list(result.get("documents") or [])
    for document in documents:
        article_examples = examples_by_article.get(int(document["article_id"]), [])
        pinned = max(
            article_examples,
            key=lambda example: training_example_score(normalized_query, example),
            default=None,
        )
        if (
            pinned is not None
            and training_example_score(normalized_query, pinned) >= EXAMPLE_MATCH_FLOOR
        ):
            document["matched_example_id"] = pinned.pk
            document["matched_example"] = pinned.question
        else:
            document["matched_example_id"] = None
            document["matched_example"] = document.get("title") or ""

    hint = None
    if documents:
        top = documents[0]
        source = _joined_article_content(int(top["article_id"])) or str(
            top.get("content") or ""
        )
        if source:
            top["content"] = source
            top["snippet"] = focused_snippet(
                source,
                normalized_query,
                SNIPPET_PREVIEW_CHARS,
            )
        hint_text = extractive_answer(source, normalized_query)
        if hint_text:
            hint = {
                "text": hint_text,
                "title": top["title"],
                "permalink": top.get("permalink") or "",
                "article_id": top["article_id"],
                "kb_slug": top.get("kb_slug") or "",
                "relevance_percent": top["relevance_percent"],
            }

    result["kb_id"] = "all_knowledge_bases"
    result["hint"] = hint
    result["documents"] = documents
    return result
