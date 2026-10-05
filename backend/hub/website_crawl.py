"""Admin website crawl → assistant_* RAG (P5-07). Not used from chat."""

from __future__ import annotations

import logging
from typing import Any, Mapping
from urllib.parse import urlparse

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from hub.assistant_admin import AssistantAdminError, _chunk_profile
from hub.kb_admin import KnowledgeBaseError, extract_document_text
from hub.models import (
    AssistantKnowledgeBase,
    AssistantWebsiteCrawlJob,
    AssistantWebsitePage,
)
from ingest.models import AssistantProductionChunk
from ingest.pipeline import checksum_for_text, chunk_text, normalize_text
from ingest.web_fetcher import (
    DEFAULT_DEPTH,
    DEFAULT_MAX_PAGES,
    FetchedPage,
    FetcherError,
    SsrfError,
    WhitelistError,
    canonicalize_url,
    crawl_website,
    hostname_of,
    is_docx_content,
    is_pdf_content,
    normalize_allowed_hosts,
    validate_fetch_url,
)

logger = logging.getLogger(__name__)

WEBSITE_ARTICLE_ID_BASE = 4_000_000_000
ACTIVE_JOB_STATUSES = (
    AssistantWebsiteCrawlJob.STATUS_QUEUED,
    AssistantWebsiteCrawlJob.STATUS_CRAWLING,
    AssistantWebsiteCrawlJob.STATUS_INDEXING,
)


def serialize_crawl_job(job: AssistantWebsiteCrawlJob | None) -> dict[str, Any] | None:
    if job is None:
        return None
    started = job.started_at.isoformat() if job.started_at else None
    finished = job.finished_at.isoformat() if job.finished_at else None
    elapsed = None
    if job.started_at and job.finished_at:
        elapsed = max(0, int((job.finished_at - job.started_at).total_seconds()))
    return {
        "id": job.pk,
        "status": job.status,
        "status_message": job.status_message,
        "pages_ok": job.pages_ok,
        "pages_4xx": job.pages_4xx,
        "pages_5xx": job.pages_5xx,
        "pages_skipped": job.pages_skipped,
        "started_at": started,
        "finished_at": finished,
        "elapsed_seconds": elapsed,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat(),
    }


def serialize_website_page(page: AssistantWebsitePage) -> dict[str, Any]:
    indexed = bool(page.extracted_text) and not page.skipped_reason
    return {
        "id": page.pk,
        "filename": page.title or page.url,
        "url": page.url,
        "content_type": page.content_type,
        "size_bytes": page.size_bytes,
        "status": "indexed" if indexed else "error",
        "status_message": page.skipped_reason,
        "chunk_count": 0,
        "index_percent": 100 if indexed else 0,
        "source_label": "Сайт",
        "permalink": page.url,
        "http_status": page.http_status,
        "readonly": True,
    }


def latest_crawl_job(kb: AssistantKnowledgeBase) -> AssistantWebsiteCrawlJob | None:
    return kb.crawl_jobs.order_by("-pk").first()


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def apply_website_settings(
    kb: AssistantKnowledgeBase,
    payload: Mapping[str, Any],
) -> AssistantKnowledgeBase:
    if "start_url" in payload:
        kb.start_url = str(payload.get("start_url") or "").strip()
    if "depth" in payload or "crawl_depth" in payload:
        raw = payload.get("depth", payload.get("crawl_depth", kb.crawl_depth))
        kb.crawl_depth = max(0, min(10, int(raw or DEFAULT_DEPTH)))
    if "max_pages" in payload:
        kb.max_pages = max(1, min(2000, int(payload.get("max_pages") or DEFAULT_MAX_PAGES)))
    if "ignore_robots" in payload:
        kb.ignore_robots = _bool(payload.get("ignore_robots"))
    if "allowed_hosts" in payload:
        kb.allowed_hosts = normalize_allowed_hosts(payload.get("allowed_hosts"))
    if kb.start_url:
        kb.source = AssistantKnowledgeBase.SOURCE_WEBSITE
    return kb


def _audit_ignore_robots(request: HttpRequest | None, kb: AssistantKnowledgeBase) -> None:
    if request is None or not kb.ignore_robots:
        return
    from audit import emit
    from audit.events import (
        CATEGORY_ADMINISTRATION,
        RESULT_SUCCESS,
        WEBSITE_CRAWL_IGNORE_ROBOTS,
    )
    from audit.service import request_context, subject_from_request

    emit(
        category=CATEGORY_ADMINISTRATION,
        event_type=WEBSITE_CRAWL_IGNORE_ROBOTS,
        result=RESULT_SUCCESS,
        subject=subject_from_request(request),
        module="hub",
        description="Admin started website crawl with robots.txt Disallow ignored",
        request=request_context(request),
        details={"kb_id" : kb.pk, "start_url": kb.start_url, "allowed_hosts": kb.allowed_hosts},
    )


def start_website_crawl(
    kb_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
    request: HttpRequest | None = None,
) -> dict[str, Any]:
    from hub.assistant_admin import get_assistant_kb

    with transaction.atomic():
        try:
            kb = AssistantKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        except AssistantKnowledgeBase.DoesNotExist as exc:
            raise AssistantAdminError("KB not found") from exc
        apply_website_settings(kb, payload)
        hosts = normalize_allowed_hosts(kb.allowed_hosts)
        if not hosts:
            raise AssistantAdminError("укажите разрешённые домены (allowed_hosts)")
        if not kb.start_url:
            raise AssistantAdminError("укажите стартовый URL сайта")
        try:
            kb.start_url = validate_fetch_url(
                kb.start_url,
                allowed_hosts=hosts,
                check_dns=False,
            )
        except (SsrfError, WhitelistError, FetcherError) as exc:
            raise AssistantAdminError(str(exc)) from exc
        if kb.crawl_jobs.filter(status__in=ACTIVE_JOB_STATUSES).exists():
            raise AssistantAdminError("обход сайта уже выполняется")
        kb.source = AssistantKnowledgeBase.SOURCE_WEBSITE
        kb.status = AssistantKnowledgeBase.STATUS_INDEXING
        kb.status_message = "Обход сайта в очереди"
        kb.save()
        job = AssistantWebsiteCrawlJob.objects.create(
            knowledge_base=kb,
            status=AssistantWebsiteCrawlJob.STATUS_QUEUED,
            status_message="В очереди",
            created_by=username,
        )
    _audit_ignore_robots(request, kb)
    enqueue_website_crawl(job.pk)
    return {
        "knowledge_base": get_assistant_kb(kb.pk),
        "job": serialize_crawl_job(job),
    }


def enqueue_website_crawl(job_id: int) -> None:
    from ingest.tasks import crawl_assistant_website

    try:
        crawl_assistant_website.delay(job_id)
    except Exception:
        logger.exception("failed to enqueue website crawl job %s", job_id)


def get_latest_crawl(kb_id: int) -> dict[str, Any]:
    from hub.assistant_admin import get_assistant_kb

    kb_payload = get_assistant_kb(kb_id)
    kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
    return {
        "knowledge_base": kb_payload,
        "job": serialize_crawl_job(latest_crawl_job(kb)),
    }


def _page_text(page: FetchedPage) -> str:
    if page.text.strip():
        return normalize_text(page.text)
    if is_pdf_content(page.content_type, page.final_url):
        filename = urlparse(page.final_url).path.rsplit("/", 1)[-1] or "page.pdf"
        if not filename.lower().endswith(".pdf"):
            filename += ".pdf"
        try:
            return extract_document_text(filename, page.body)
        except KnowledgeBaseError:
            return ""
    if is_docx_content(page.content_type, page.final_url):
        filename = urlparse(page.final_url).path.rsplit("/", 1)[-1] or "page.docx"
        if not filename.lower().endswith(".docx"):
            filename += ".docx"
        try:
            return extract_document_text(filename, page.body)
        except KnowledgeBaseError:
            return ""
    return ""


def _upsert_page(kb: AssistantKnowledgeBase, fetched: FetchedPage) -> AssistantWebsitePage:
    url = canonicalize_url(fetched.final_url or fetched.url)
    text = "" if fetched.skipped_reason else _page_text(fetched)
    title = (fetched.title or hostname_of(url) or url)[:500]
    defaults = {
        "title": title,
        "extracted_text": text,
        "http_status": fetched.status,
        "content_type": (fetched.content_type or "")[:128],
        "size_bytes": len(fetched.body or b""),
        "checksum": checksum_for_text(text) if text else "",
        "skipped_reason": fetched.skipped_reason,
    }
    page, created = AssistantWebsitePage.objects.get_or_create(
        knowledge_base=kb,
        url=url,
        defaults={**defaults, "article_id": WEBSITE_ARTICLE_ID_BASE},
    )
    if created:
        page.article_id = WEBSITE_ARTICLE_ID_BASE + page.pk
        page.save(update_fields=("article_id",))
        return page
    for key, value in defaults.items():
        setattr(page, key, value)
    page.save()
    return page


def _index_website_pages(kb: AssistantKnowledgeBase) -> int:
    from core.embeddings import embed_texts

    chunk_size, overlap, embedding_model = _chunk_profile()
    total = 0
    pages = list(kb.website_pages.exclude(extracted_text="").order_by("pk"))
    for page in pages:
        text = normalize_text(page.extracted_text)
        if not text:
            continue
        chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        vectors = embed_texts(chunks, is_query=False)
        checksum = page.checksum or checksum_for_text(text)
        with transaction.atomic():
            AssistantProductionChunk.objects.filter(
                kb_slug=kb.slug,
                article_id=page.article_id,
            ).delete()
            AssistantProductionChunk.objects.bulk_create(
                [
                    AssistantProductionChunk(
                        kb_slug=kb.slug,
                        article_id=page.article_id,
                        version_id=page.pk,
                        chunk_index=index,
                        title=page.title or page.url,
                        content=chunk,
                        permalink=page.url,
                        locale="ru",
                        visibility_scope=["assistant", kb.scope],
                        checksum=checksum,
                        embedding_model=embedding_model,
                        embedding=vectors[index],
                        is_active=True,
                    )
                    for index, chunk in enumerate(chunks)
                ]
            )
        total += len(chunks)
    return total


def run_website_crawl(job_id: int, *, http_get=None) -> dict[str, Any]:
    job = AssistantWebsiteCrawlJob.objects.select_related("knowledge_base").get(pk=job_id)
    kb = job.knowledge_base
    job.status = AssistantWebsiteCrawlJob.STATUS_CRAWLING
    job.status_message = "Обход сайта"
    job.pages_ok = 0
    job.pages_4xx = 0
    job.pages_5xx = 0
    job.pages_skipped = 0
    job.started_at = timezone.now()
    job.finished_at = None
    job.save()
    kb.status = AssistantKnowledgeBase.STATUS_INDEXING
    kb.status_message = "Обход сайта"
    kb.save(update_fields=("status", "status_message", "updated_at"))
    kb.website_pages.filter(skipped_reason__gt="").delete()
    kb.website_pages.filter(extracted_text="", skipped_reason="").delete()

    def _progress(item: FetchedPage) -> None:
        page = _upsert_page(kb, item)
        if item.skipped_reason:
            job.pages_skipped += 1
        elif 400 <= item.status < 500:
            job.pages_4xx += 1
        elif item.status >= 500:
            job.pages_5xx += 1
        elif page.extracted_text:
            job.pages_ok += 1
        else:
            job.pages_skipped += 1
        job.status_message = f"Обход сайта: {job.pages_ok} стр."
        job.save(
            update_fields=(
                "pages_ok",
                "pages_4xx",
                "pages_5xx",
                "pages_skipped",
                "status_message",
            )
        )
        kb.document_count = job.pages_ok
        kb.status_message = job.status_message
        kb.save(update_fields=("document_count", "status_message", "updated_at"))

    try:
        fetched = crawl_website(
            kb.start_url,
            allowed_hosts=kb.allowed_hosts,
            depth=kb.crawl_depth,
            max_pages=kb.max_pages,
            ignore_robots=kb.ignore_robots,
            http_get=http_get,
            on_page=_progress,
        )
        pages_ok = pages_4xx = pages_5xx = pages_skipped = 0
        for item in fetched:
            page = _upsert_page(kb, item)
            if item.skipped_reason:
                pages_skipped += 1
            elif 400 <= item.status < 500:
                pages_4xx += 1
            elif item.status >= 500:
                pages_5xx += 1
            elif page.extracted_text:
                pages_ok += 1
            else:
                pages_skipped += 1
        seen_urls = {
            canonicalize_url(item.final_url or item.url)
            for item in fetched
        }
        kb.website_pages.exclude(url__in=seen_urls).delete()
        job.pages_ok = pages_ok
        job.pages_4xx = pages_4xx
        job.pages_5xx = pages_5xx
        job.pages_skipped = pages_skipped
        job.status = AssistantWebsiteCrawlJob.STATUS_INDEXING
        job.status_message = "Индексация страниц"
        job.save()
        kb.status_message = "Индексация страниц сайта"
        kb.save(update_fields=("status_message", "updated_at"))
        total_chunks = _index_website_pages(kb)
        kb.document_count = kb.website_pages.exclude(extracted_text="").count()
        kb.chunk_count = total_chunks
        kb.last_reindexed_at = timezone.now()
        if pages_ok == 0:
            job.status = AssistantWebsiteCrawlJob.STATUS_FAILED
            job.status_message = (
                "Не удалось извлечь текст страниц. "
                "Проверьте редирект www/без www и список доменов."
            )
            job.finished_at = timezone.now()
            job.save()
            kb.status = AssistantKnowledgeBase.STATUS_ERROR
            kb.status_message = job.status_message
            kb.save()
            return {"status": "failed", "pages_ok": 0, "chunks": 0}
        job.status = AssistantWebsiteCrawlJob.STATUS_READY
        job.status_message = "Индекс актуален"
        job.finished_at = timezone.now()
        job.save()
        kb.status = AssistantKnowledgeBase.STATUS_READY
        kb.status_message = "Индекс актуален"
        kb.save()
        return {"status": "ready", "pages_ok": pages_ok, "chunks": total_chunks}
    except Exception as exc:
        logger.exception("website crawl job %s failed", job_id)
        job.status = AssistantWebsiteCrawlJob.STATUS_FAILED
        job.status_message = str(exc)[:500]
        job.finished_at = timezone.now()
        job.save()
        kb.status = AssistantKnowledgeBase.STATUS_ERROR
        kb.status_message = str(exc)[:500]
        kb.save(update_fields=("status", "status_message", "updated_at"))
        raise
