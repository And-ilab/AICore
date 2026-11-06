"""INT-10 full load: list published SUZ articles and index them."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from django.conf import settings

from ingest.bitrix_client import (
    ArticleNotFound,
    BitrixAuthError,
    BitrixCatalogClient,
    BitrixClientError,
    NormalizedArticle,
    get_bitrix_catalog_client,
)
from ingest.models import CCProductionChunk
from ingest.pipeline import checksum_for_text, ingest_payload, normalize_text
from ingest.schema import SuzPayload, SuzPayloadError


@dataclass
class ArticleFailure:
    article_id: int
    error: str


@dataclass
class FullLoadResult:
    indexed: int = 0
    unchanged: int = 0
    skipped: int = 0
    deleted: int = 0
    errors: int = 0
    failures: list[ArticleFailure] = field(default_factory=list)
    next_start: int | None = None
    listed_ids: list[int] = field(default_factory=list)


class FullLoadConfigError(BitrixClientError):
    """iblock id or command arguments cannot be used."""


class FullLoadPageError(BitrixClientError):
    """A list page failed after retries. Resume from ``start``."""

    def __init__(self, message: str, *, start: int, result: FullLoadResult) -> None:
        super().__init__(message)
        self.start = start
        self.result = result


class FullLoadArticleError(Exception):
    def __init__(self, message: str, *, skip: bool = False) -> None:
        super().__init__(message)
        self.skip = skip


def resolve_iblock_id(explicit: int | None) -> int:
    allowed = getattr(settings, "SUZ_ALLOWED_IBLOCK_IDS", frozenset())
    if explicit is None:
        if len(allowed) == 1:
            return next(iter(allowed))
        raise FullLoadConfigError(
            "Pass --iblock-id (SUZ_ALLOWED_IBLOCK_IDS is empty or lists several ids)"
        )
    if explicit <= 0:
        raise FullLoadConfigError("--iblock-id must be a positive integer")
    if allowed and explicit not in allowed:
        raise FullLoadConfigError(
            f"iblock_id {explicit} is not in SUZ_ALLOWED_IBLOCK_IDS"
        )
    return explicit


def run_full_load(
    *,
    iblock_id: int,
    start: int = 0,
    limit: int = 0,
    dry_run: bool = False,
    client: BitrixCatalogClient | None = None,
) -> FullLoadResult:
    """
    Pull published articles and write them through the same ingest pipeline
    as a Model B publish webhook. Does not move the INT-09 cursor.
    """
    if start < 0:
        raise FullLoadConfigError("--start must be >= 0")
    if limit < 0:
        raise FullLoadConfigError("--limit must be >= 0")

    catalog = client if client is not None else get_bitrix_catalog_client()
    result = FullLoadResult(next_start=start)
    processed = 0
    page_start = start
    seen_starts: set[int] = set()

    while page_start not in seen_starts:
        seen_starts.add(page_start)
        try:
            page = catalog.list_articles(iblock_id, start=page_start)
        except BitrixAuthError:
            raise
        except BitrixClientError as exc:
            result.next_start = page_start
            raise FullLoadPageError(
                str(exc),
                start=page_start,
                result=result,
            ) from exc

        if not page.article_ids:
            result.next_start = None
            return result

        for article_id in page.article_ids:
            if limit and processed >= limit:
                result.next_start = page_start
                return result
            processed += 1
            result.listed_ids.append(article_id)
            if dry_run:
                continue
            _ingest_one(catalog, iblock_id, article_id, result)

        if limit and processed >= limit:
            result.next_start = _resume_start(page_start, page.next_start)
            return result
        if page.next_start is None or page.next_start <= page_start:
            result.next_start = None
            return result
        page_start = page.next_start
        result.next_start = page_start

    result.next_start = None
    return result


def article_to_event(article: NormalizedArticle) -> dict:
    status = (article.status or "published").strip()
    if status != "published":
        raise FullLoadArticleError(f"status={status}", skip=True)

    version_id = _coerce_version_id(article.version_id, article.article_id)
    if not article.permalink:
        raise FullLoadArticleError("permalink is missing")
    if not article.title:
        raise FullLoadArticleError("title is missing")
    if not article.body_plain and not article.body_html:
        raise FullLoadArticleError("article body is empty")

    if article.visibility_scope is None:
        if not article.apply_default_scope:
            raise FullLoadArticleError("visibility_scope is missing")
        scope = ["kc_operator"]
    else:
        scope = [item for item in article.visibility_scope if item]
        if not scope:
            raise FullLoadArticleError("visibility_scope is empty")

    checksum = checksum_for_text(
        normalize_text(article.body_plain, article.body_html)
    )
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "article.version_published",
        "occurred_at": _occurred_at(article.updated_at),
        "article_id": article.article_id,
        "iblock_id": article.iblock_id,
        "version_id": version_id,
        "version_number": article.version_number or 1,
        "is_current": True,
        "status": "published",
        "title": article.title,
        "preview": article.preview,
        "body_html": article.body_html,
        "body_plain": article.body_plain,
        "permalink": article.permalink,
        "locale": article.locale or "ru",
        "visibility_scope": scope,
        "checksum": checksum,
        "changed_fields": ["DETAIL_TEXT"],
    }
    if article.section_id:
        event["section_id"] = article.section_id
    return event


def _ingest_one(
    catalog: BitrixCatalogClient,
    iblock_id: int,
    article_id: int,
    result: FullLoadResult,
) -> None:
    try:
        article = catalog.get_article(iblock_id, article_id)
    except ArticleNotFound:
        if CCProductionChunk.objects.filter(article_id=article_id).exists():
            _ingest_deleted(iblock_id, article_id, result)
        else:
            result.skipped += 1
        return
    except BitrixAuthError:
        raise
    except BitrixClientError as exc:
        _fail(result, article_id, str(exc))
        return

    try:
        event = article_to_event(article)
        payload = SuzPayload.from_mapping(event)
        ingested = ingest_payload(payload)
    except FullLoadArticleError as exc:
        if exc.skip:
            result.skipped += 1
        else:
            _fail(result, article_id, str(exc))
        return
    except SuzPayloadError as exc:
        _fail(result, article_id, "validation: " + ", ".join(exc.fields))
        return

    if ingested.outcome == "indexed":
        result.indexed += 1
    elif ingested.outcome == "unchanged":
        result.unchanged += 1
    elif ingested.outcome == "hard_deleted":
        result.deleted += 1
    else:
        result.skipped += 1


def _ingest_deleted(
    iblock_id: int,
    article_id: int,
    result: FullLoadResult,
) -> None:
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": "article.deleted",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "article_id": article_id,
        "iblock_id": iblock_id,
        "changed_fields": [],
    }
    try:
        payload = SuzPayload.from_mapping(event)
        ingested = ingest_payload(payload)
    except SuzPayloadError as exc:
        _fail(result, article_id, "validation: " + ", ".join(exc.fields))
        return
    if ingested.outcome == "hard_deleted":
        result.deleted += 1
    else:
        result.skipped += 1


def _fail(result: FullLoadResult, article_id: int, error: str) -> None:
    result.errors += 1
    result.failures.append(ArticleFailure(article_id=article_id, error=error[:300]))


def _coerce_version_id(value: object, article_id: int) -> int:
    if value is None or value == "":
        return article_id
    if isinstance(value, bool):
        raise FullLoadArticleError("version_id is not an integer")
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        if parsed > 0:
            return parsed
    raise FullLoadArticleError(f"version_id {value!r} is not an integer")


def _occurred_at(value: str | None) -> str:
    if value:
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed.isoformat()
    return datetime.now(timezone.utc).isoformat()


def _resume_start(page_start: int, next_start: int | None) -> int | None:
    if next_start is None or next_start <= page_start:
        return None
    return next_start
