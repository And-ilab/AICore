"""Assistant admin stubs: assistant_* KB, prompts CRUD, tools registry (III.6)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from hub.kb_admin import (
    KnowledgeBaseError,
    document_index_percent,
    extract_document_text,
    write_index_progress,
)
from hub.models import (
    AssistantCapability,
    AssistantKnowledgeBase,
    AssistantKnowledgeBaseDocument,
    AssistantPromptTemplate,
)
from core.embeddings import embed_texts
from ingest.models import AssistantProductionChunk
from ingest.pipeline import (
    checksum_for_text,
    chunk_text,
    normalize_text,
)

ARTICLE_ID_BASE = 3_000_000_000
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
DEFAULT_EMBEDDING_MODEL = "dev-embedding"

FORBIDDEN_KB_SLUGS = frozenset({"cc_production", "cc-production", "suz_cc"})
ASSISTANT_SLUG_PREFIX = "assistant_"
SLUG_RE = re.compile(r"^[a-z0-9_]+$")
_CYRILLIC_MAP = str.maketrans(
    {
        "а": "a",
        "б": "b",
        "в": "v",
        "г": "g",
        "д": "d",
        "е": "e",
        "ё": "e",
        "ж": "zh",
        "з": "z",
        "и": "i",
        "й": "y",
        "к": "k",
        "л": "l",
        "м": "m",
        "н": "n",
        "о": "o",
        "п": "p",
        "р": "r",
        "с": "s",
        "т": "t",
        "у": "u",
        "ф": "f",
        "х": "h",
        "ц": "ts",
        "ч": "ch",
        "ш": "sh",
        "щ": "sch",
        "ъ": "",
        "ы": "y",
        "ь": "",
        "э": "e",
        "ю": "yu",
        "я": "ya",
    }
)

DEFAULT_CAPABILITIES: tuple[dict[str, Any], ...] = (
    {
        "code": "rag_kb",
        "name": "Поиск по KB (RAG)",
        "description": "Retrieval по БЗ: ручная загрузка и СУЗ Битрикс — единый раздел «Базы знаний».",
        "deep_link": "kb_admin",
        "category": "rag",
        "sort_order": 10,
        "enabled": True,
    },
    {
        "code": "external_sources",
        "name": "Внешние источники",
        "description": "Адаптеры внешних систем (не CRUD БЗ). Базы знаний СУЗ — в «Базы знаний».",
        "deep_link": "data_sources",
        "category": "integration",
        "sort_order": 20,
        "enabled": True,
    },
    {
        "code": "generate_document",
        "name": "Генерация документов",
        "description": "Word/PDF/Excel/PPT/BPMN по шаблону банка.",
        "deep_link": "assistant_tools",
        "category": "tool",
        "sort_order": 30,
        "enabled": True,
    },
    {
        "code": "rpa",
        "name": "RPA",
        "description": "Whitelist сценариев с confirm (VII.5 D4).",
        "deep_link": "assistant_tools",
        "category": "tool",
        "sort_order": 40,
        "enabled": False,
    },
    {
        "code": "sql_code",
        "name": "SQL / код",
        "description": "Read-only SQL и sandbox кода (III.6.5).",
        "deep_link": "assistant_tools",
        "category": "tool",
        "sort_order": 50,
        "enabled": False,
    },
    {
        "code": "summarize",
        "name": "Саммаризация файлов",
        "description": "Аудио/видео/документы.",
        "deep_link": "capabilities",
        "category": "tool",
        "sort_order": 60,
        "enabled": True,
    },
    {
        "code": "translate",
        "name": "Перевод RU↔EN",
        "description": "Двуязычный ответ, не формат файла.",
        "deep_link": "prompts_assistant",
        "category": "tool",
        "sort_order": 70,
        "enabled": True,
    },
    {
        "code": "clarify",
        "name": "Уточняющие вопросы",
        "description": "Низкая релевантность → уточнение.",
        "deep_link": "qu_admin",
        "category": "qu",
        "sort_order": 80,
        "enabled": True,
    },
)

DEFAULT_PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "System · assistant_bank",
        "prompt_type": AssistantPromptTemplate.TYPE_SYSTEM,
        "scope": "bank",
        "event_trigger": "",
        "body": (
            "Ты внутренний ИИ-ассистент банка. Отвечай только на основе "
            "индексов {{kb}} и контекста подразделения {{dept}}. "
            "Пользователь: {{user}}."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
        "kb_slug": "assistant_hr",
    },
    {
        "name": "Scope · ИБ",
        "prompt_type": AssistantPromptTemplate.TYPE_SCOPE,
        "scope": "security",
        "event_trigger": "",
        "body": "Не раскрывай внутренние политики ИБ вне AD-scope пользователя.",
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
        "kb_slug": "assistant_security",
    },
)

# Task skills for «Навыки и инструменты» (orchestration events).
DEFAULT_TASK_SKILL_PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "сессии пользователя",
        "event_trigger": "Начало сессии",
        "body": (
            "Учитывай контекст текущей сессии {{session_id}} "
            "и роль пользователя {{dept}}."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
    },
    {
        "name": "общение в диалоге",
        "event_trigger": "Ответ в чате",
        "body": (
            "Отвечай профессионально и кратко. "
            "Сохраняй тон банка без канцелярита."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
    },
    {
        "name": "уточняющий вопрос",
        "event_trigger": "Запрос уточнения (QU)",
        "body": (
            "Сформулируй один короткий уточняющий вопрос, чтобы сузить тему. "
            "Не задавай более двух уточнений подряд без попытки ответа."
        ),
        "status": AssistantPromptTemplate.STATUS_DRAFT,
    },
    {
        "name": "контекст истории",
        "event_trigger": "Контекст истории (auto/manual)",
        "body": (
            "Используй последние {{history_limit}} сообщений из истории "
            "диалога, если они релевантны запросу."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
    },
    {
        "name": "перевод en→ru",
        "event_trigger": "Перевод EN→RU",
        "body": (
            "Переведи текст на русский язык, сохраняя терминологию банка "
            "и форматирование."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
    },
    {
        "name": "перевод ru→en",
        "event_trigger": "Перевод RU→EN",
        "body": (
            "Translate the text to English, preserving banking terminology "
            "and formatting."
        ),
        "status": AssistantPromptTemplate.STATUS_PUBLISHED,
    },
)

TASK_EVENT_TRIGGERS: tuple[str, ...] = tuple(
    item["event_trigger"] for item in DEFAULT_TASK_SKILL_PROMPTS
)

DEFAULT_KBS: tuple[dict[str, str], ...] = (
    {
        "name": "HR policies",
        "slug": "assistant_hr",
        "scope": "hr",
        "description": "Корпоративные регламенты HR",
    },
    {
        "name": "IT runbooks",
        "slug": "assistant_it",
        "scope": "it",
        "description": "ИТ-инструкции и доступы",
    },
    {
        "name": "Security & compliance",
        "slug": "assistant_security",
        "scope": "security",
        "description": "Политики ИБ",
    },
)


class AssistantAdminError(ValueError):
    """Invalid assistant admin operation."""


def ensure_assistant_seed(username: str = "system") -> None:
    """Idempotent seed for stub admin screens.

    Knowledge bases are NOT auto-created — the assistant chat catalog must
    mirror real Hub data (empty DB → empty dropdown).
    """
    if not AssistantPromptTemplate.objects.exists():
        for item in DEFAULT_PROMPTS:
            AssistantPromptTemplate.objects.create(
                name=item["name"],
                prompt_type=item["prompt_type"],
                scope=item["scope"],
                event_trigger=item.get("event_trigger", ""),
                body=item["body"],
                status=item["status"],
                kb_slug=item["kb_slug"],
                updated_by=username,
            )
    for item in DEFAULT_TASK_SKILL_PROMPTS:
        matches = list(
            AssistantPromptTemplate.objects.filter(
                name=item["name"],
                prompt_type=AssistantPromptTemplate.TYPE_TASK,
            ).order_by("id")
        )
        if matches:
            prompt = matches[0]
            # Collapse accidental duplicates from repeated seed runs.
            if len(matches) > 1:
                AssistantPromptTemplate.objects.filter(
                    pk__in=[row.pk for row in matches[1:]]
                ).delete()
            if not prompt.event_trigger:
                prompt.event_trigger = item["event_trigger"]
                prompt.save(update_fields=("event_trigger", "updated_at"))
        else:
            AssistantPromptTemplate.objects.create(
                name=item["name"],
                prompt_type=AssistantPromptTemplate.TYPE_TASK,
                scope="bank",
                event_trigger=item["event_trigger"],
                body=item["body"],
                status=item["status"],
                kb_slug="",
                updated_by=username,
            )
    for item in DEFAULT_CAPABILITIES:
        capability, created = AssistantCapability.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "description": item["description"],
                "deep_link": item["deep_link"],
                "category": item["category"],
                "sort_order": item["sort_order"],
                "enabled": item["enabled"],
            },
        )
        if not created and (
            capability.deep_link != item["deep_link"]
            or capability.description != item["description"]
            or capability.name != item["name"]
        ):
            capability.deep_link = item["deep_link"]
            capability.description = item["description"]
            capability.name = item["name"]
            capability.save(
                update_fields=("deep_link", "description", "name", "updated_at")
            )


def _slugify_assistant_name(raw: str) -> str:
    """ASCII slug from RU/EN name (Cyrillic is transliterated first)."""
    lowered = (raw or "").strip().casefold()
    transliterated = lowered.translate(_CYRILLIC_MAP)
    base = slugify(transliterated, allow_unicode=False).replace("-", "_")
    return base or "kb"


def _normalize_assistant_slug(raw: str) -> str:
    value = (raw or "").strip().lower().replace("-", "_")
    if value in FORBIDDEN_KB_SLUGS or value == "cc_production":
        raise AssistantAdminError(
            "assistant KB must not use cc_production namespace"
        )
    if not value.startswith(ASSISTANT_SLUG_PREFIX):
        value = f"{ASSISTANT_SLUG_PREFIX}{_slugify_assistant_name(value)}"
    value = value.replace("-", "_")
    if not SLUG_RE.match(value):
        raise AssistantAdminError("slug must be snake_case assistant_*")
    if value in FORBIDDEN_KB_SLUGS:
        raise AssistantAdminError(
            "assistant KB must not use cc_production namespace"
        )
    return value


def _unique_assistant_slug(raw: str) -> str:
    base = _normalize_assistant_slug(raw)
    candidate = base
    index = 2
    while AssistantKnowledgeBase.objects.filter(slug=candidate).exists():
        candidate = f"{base}_{index}"
        index += 1
    return candidate


def assistant_source_download_url(
    *,
    kb_slug: str,
    article_id: int | str,
) -> str:
    """Permalink opened from chat citations → original file download."""
    return (
        "/api/v1/assistant/sources/download"
        f"?kb_slug={quote(str(kb_slug), safe='')}"
        f"&article_id={quote(str(article_id), safe='')}"
    )


def _kb_storage_root() -> Path:
    root = Path(getattr(settings, "ASSISTANT_KB_STORAGE_ROOT", ""))
    if not str(root):
        root = Path(settings.BASE_DIR) / "var" / "assistant-kb"
    root.mkdir(parents=True, exist_ok=True)
    return root


def store_assistant_original(
    *,
    kb_id: int,
    document_id: int,
    filename: str,
    data: bytes,
) -> str:
    """Persist original bytes; return relative path under storage root."""
    safe_name = Path(filename).name.strip() or "document.bin"
    rel = f"{kb_id}/{document_id}/{safe_name}"
    path = _kb_storage_root() / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return rel.replace("\\", "/")


def resolve_assistant_original_path(
    document: AssistantKnowledgeBaseDocument,
) -> Path | None:
    rel = (document.original_relpath or "").strip()
    if not rel:
        return None
    path = (_kb_storage_root() / rel).resolve()
    root = _kb_storage_root().resolve()
    if root not in path.parents and path != root:
        return None
    if not path.is_file():
        return None
    return path


def delete_assistant_original(document: AssistantKnowledgeBaseDocument) -> None:
    path = resolve_assistant_original_path(document)
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError:
        pass


def serialize_document(document: AssistantKnowledgeBaseDocument) -> dict[str, Any]:
    return {
        "id": document.pk,
        "filename": document.filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "status": document.status,
        "status_message": document.status_message,
        "chunk_count": document.chunk_count,
        "has_original": bool(document.original_relpath),
        "download_url": assistant_source_download_url(
            kb_slug=document.knowledge_base.slug,
            article_id=document.article_id,
        ),
        "uploaded_at": document.uploaded_at.isoformat(),
        "indexed_at": (
            document.indexed_at.isoformat() if document.indexed_at else None
        ),
        "uploaded_by": document.uploaded_by,
        "index_percent": document_index_percent(
            document.status, document.status_message
        ),
    }


def serialize_kb(
    kb: AssistantKnowledgeBase,
    *,
    include_documents: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": kb.pk,
        "name": kb.name,
        "slug": kb.slug,
        "namespace": "assistant_*",
        "isolated_from": "cc_production",
        "scope": kb.scope,
        "description": kb.description,
        "status": kb.status,
        "status_message": kb.status_message,
        "document_count": kb.document_count,
        "chunk_count": kb.chunk_count,
        "last_reindexed_at": (
            kb.last_reindexed_at.isoformat() if kb.last_reindexed_at else None
        ),
        "created_at": kb.created_at.isoformat(),
        "updated_at": kb.updated_at.isoformat(),
        "created_by": kb.created_by,
        "source": kb.source or AssistantKnowledgeBase.SOURCE_MANUAL,
        "source_label": (
            "Сайт"
            if kb.source == AssistantKnowledgeBase.SOURCE_WEBSITE
            else "Ручная загрузка"
        ),
        "start_url": kb.start_url,
        "crawl_depth": kb.crawl_depth,
        "max_pages": kb.max_pages,
        "ignore_robots": kb.ignore_robots,
        "allowed_hosts": list(kb.allowed_hosts or []),
    }
    from hub.website_crawl import latest_crawl_job, serialize_crawl_job, serialize_website_page

    job = latest_crawl_job(kb)
    payload["latest_job"] = serialize_crawl_job(job)
    file_docs = [
        serialize_document(document) for document in kb.documents.all()
    ]
    from ingest.web_fetcher import is_sitemap_url

    page_docs = [
        serialize_website_page(page)
        for page in kb.website_pages.all()
        if page.extracted_text and not is_sitemap_url(page.url)
    ]
    if include_documents:
        payload["documents"] = file_docs + page_docs
        payload["pages"] = page_docs
        percents = [int(doc["index_percent"]) for doc in payload["documents"]]
        payload["index_percent"] = (
            round(sum(percents) / len(percents)) if percents else 0
        )
        if kb.status == AssistantKnowledgeBase.STATUS_INDEXING and percents:
            payload["index_percent"] = min(payload["index_percent"], 99)
    else:
        docs = list(kb.documents.all())
        if docs:
            percents = [
                document_index_percent(item.status, item.status_message)
                for item in docs
            ]
            payload["index_percent"] = round(sum(percents) / len(percents))
        else:
            payload["index_percent"] = (
                100
                if kb.status == AssistantKnowledgeBase.STATUS_READY
                and kb.document_count
                else 0
            )
        if kb.status == AssistantKnowledgeBase.STATUS_INDEXING:
            payload["index_percent"] = min(int(payload["index_percent"]), 99)
    if kb.source == AssistantKnowledgeBase.SOURCE_WEBSITE:
        payload["index_percent"] = _website_index_percent(kb, job)
    return payload


def _website_index_percent(kb: AssistantKnowledgeBase, job) -> int:
    if kb.status == AssistantKnowledgeBase.STATUS_READY and kb.document_count:
        return 100
    if job is None:
        return 0
    if job.status == "ready":
        return 100 if kb.document_count or int(job.pages_ok or 0) else 0
    if job.status == "failed":
        return 0
    if job.status == "indexing":
        return 85
    if kb.max_pages:
        return max(5, min(80, round(100 * int(job.pages_ok) / kb.max_pages)))
    return 10


def get_assistant_kb(kb_id: int) -> dict[str, Any]:
    try:
        kb = AssistantKnowledgeBase.objects.prefetch_related(
            "documents", "website_pages", "crawl_jobs"
        ).get(pk=kb_id)
    except AssistantKnowledgeBase.DoesNotExist as exc:
        raise AssistantAdminError("KB not found") from exc
    return serialize_kb(kb, include_documents=True)


def _chunk_profile() -> tuple[int, int, str]:
    try:
        from core.model_registry import ModelRegistry

        profile = ModelRegistry.load().get_profile("kb_cc_production")
        return (
            profile.chunk_size_tokens,
            profile.chunk_overlap_tokens,
            profile.embedding_model,
        )
    except Exception:
        return DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_EMBEDDING_MODEL


def serialize_prompt(prompt: AssistantPromptTemplate) -> dict[str, Any]:
    return {
        "id": prompt.pk,
        "name": prompt.name,
        "prompt_type": prompt.prompt_type,
        "scope": prompt.scope,
        "event_trigger": prompt.event_trigger,
        "body": prompt.body,
        "status": prompt.status,
        "version": prompt.version,
        "kb_slug": prompt.kb_slug,
        "updated_by": prompt.updated_by,
        "created_at": prompt.created_at.isoformat(),
        "updated_at": prompt.updated_at.isoformat(),
    }


def serialize_capability(item: AssistantCapability) -> dict[str, Any]:
    return {
        "id": item.pk,
        "code": item.code,
        "name": item.name,
        "description": item.description,
        "enabled": item.enabled,
        "deep_link": item.deep_link,
        "category": item.category,
        "sort_order": item.sort_order,
        "updated_at": item.updated_at.isoformat(),
    }


def list_assistant_kbs(*, seed: bool = False) -> list[dict[str, Any]]:
    """Return assistant_* KBs. Do not invent stub rows unless seed=True (tests/demo)."""
    if seed:
        ensure_assistant_seed()
    return [serialize_kb(item) for item in AssistantKnowledgeBase.objects.all()]


def list_chat_knowledge_bases(*, seed: bool = False) -> list[dict[str, Any]]:
    """Chat dropdown catalog: assistant_* + CC/SUZ rows from settings «Базы знаний»."""
    from hub.kb_admin import ensure_suz_knowledge_base, list_knowledge_bases

    if seed:
        ensure_assistant_seed()
    ensure_suz_knowledge_base()

    items: list[dict[str, Any]] = []
    for item in list_assistant_kbs(seed=False):
        origin = item.get("source") or AssistantKnowledgeBase.SOURCE_MANUAL
        items.append(
            {
                **item,
                "id": f"assistant:{item['id']}",
                "source": "assistant",
                "source_label": "Ассистент",
                "catalog": "assistant",
                "load_kind": (
                    "website"
                    if origin == AssistantKnowledgeBase.SOURCE_WEBSITE
                    else "article"
                ),
            }
        )
    for payload in list_knowledge_bases():
        items.append(
            {
                "id": f"cc:{payload['id']}",
                "name": payload["name"],
                "slug": payload["slug"],
                "description": payload.get("description") or "",
                "document_count": payload.get("document_count") or 0,
                "chunk_count": payload.get("chunk_count") or 0,
                "status": payload.get("status") or "",
                "status_message": payload.get("status_message") or "",
                "source": payload.get("source") or "manual",
                "source_label": payload.get("source_label") or "КЦ",
                "readonly": bool(payload.get("readonly")),
                "namespace": "cc_production",
                "catalog": "cc",
                "load_kind": "article",
            }
        )
    items.sort(key=lambda row: str(row.get("name") or "").casefold())
    return items


def create_assistant_kb(
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    if not name:
        raise AssistantAdminError("Укажите название базы знаний")
    slug_raw = str(payload.get("slug") or name)
    slug = _unique_assistant_slug(slug_raw)
    if AssistantKnowledgeBase.objects.filter(name=name).exists():
        raise AssistantAdminError(
            f"База с названием «{name}» уже существует. "
            "Выберите другое имя."
        )
    source = str(payload.get("source") or AssistantKnowledgeBase.SOURCE_MANUAL).strip()
    if source not in {
        AssistantKnowledgeBase.SOURCE_MANUAL,
        AssistantKnowledgeBase.SOURCE_WEBSITE,
    }:
        raise AssistantAdminError("source must be manual or website")
    from ingest.web_fetcher import normalize_allowed_hosts

    allowed_hosts = normalize_allowed_hosts(payload.get("allowed_hosts"))
    start_url = str(payload.get("start_url") or "").strip()
    if source == AssistantKnowledgeBase.SOURCE_WEBSITE:
        if not start_url:
            raise AssistantAdminError("укажите стартовый URL сайта")
        if not allowed_hosts:
            raise AssistantAdminError("укажите разрешённые домены (allowed_hosts)")
    kb = AssistantKnowledgeBase.objects.create(
        name=name,
        slug=slug,
        scope=str(payload.get("scope") or "department")[:64],
        description=str(payload.get("description") or ""),
        source=source,
        start_url=start_url,
        crawl_depth=max(0, min(10, int(payload.get("depth") or payload.get("crawl_depth") or 1))),
        max_pages=max(1, min(2000, int(payload.get("max_pages") or 15))),
        ignore_robots=str(payload.get("ignore_robots") or "").lower()
        in {"1", "true", "yes", "on"}
        or payload.get("ignore_robots") is True,
        allowed_hosts=allowed_hosts,
        status=AssistantKnowledgeBase.STATUS_IDLE,
        created_by=username,
    )
    return serialize_kb(kb, include_documents=True)


def delete_assistant_kb(kb_id: int) -> None:
    try:
        kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
    except AssistantKnowledgeBase.DoesNotExist as exc:
        raise AssistantAdminError("KB not found") from exc
    if not kb.slug.startswith(ASSISTANT_SLUG_PREFIX):
        raise AssistantAdminError("refusing to delete non-assistant namespace")
    article_ids = list(kb.documents.values_list("article_id", flat=True))
    article_ids.extend(kb.website_pages.values_list("article_id", flat=True))
    if article_ids:
        AssistantProductionChunk.objects.filter(
            kb_slug=kb.slug,
            article_id__in=article_ids,
        ).delete()
    kb.delete()


def upload_assistant_document(
    kb_id: int,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    username: str = "",
    reindex: bool = False,
) -> dict[str, Any]:
    """Store a document. Reindex is optional and runs outside the write txn."""
    with transaction.atomic():
        try:
            kb = AssistantKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        except AssistantKnowledgeBase.DoesNotExist as exc:
            raise AssistantAdminError("KB not found") from exc
        if not kb.slug.startswith(ASSISTANT_SLUG_PREFIX):
            raise AssistantAdminError("refusing to write non-assistant namespace")
        cleaned_name = Path(filename).name.strip()
        if not cleaned_name:
            raise AssistantAdminError("filename is required")
        try:
            text = extract_document_text(cleaned_name, data)
        except KnowledgeBaseError as exc:
            raise AssistantAdminError(str(exc)) from exc
        provisional_article_id = ARTICLE_ID_BASE + (
            AssistantKnowledgeBaseDocument.objects.count() + 1
        ) * 10_000 + (kb.pk % 10_000)
        while AssistantKnowledgeBaseDocument.objects.filter(
            article_id=provisional_article_id
        ).exists():
            provisional_article_id += 1
        document = AssistantKnowledgeBaseDocument.objects.create(
            knowledge_base=kb,
            filename=cleaned_name,
            content_type=content_type or "",
            size_bytes=len(data),
            status=AssistantKnowledgeBaseDocument.STATUS_UPLOADED,
            extracted_text=text,
            uploaded_by=username,
            article_id=provisional_article_id,
        )
        document.article_id = ARTICLE_ID_BASE + document.pk
        document.save(update_fields=("article_id",))
        relpath = store_assistant_original(
            kb_id=kb.pk,
            document_id=document.pk,
            filename=cleaned_name,
            data=data,
        )
        document.original_relpath = relpath
        document.save(update_fields=("original_relpath",))
        kb.document_count = kb.documents.count()
        kb.status = AssistantKnowledgeBase.STATUS_IDLE
        kb.status_message = "Документ загружен, требуется переиндексация"
        kb.save(
            update_fields=(
                "document_count",
                "status",
                "status_message",
                "updated_at",
            )
        )
        document_id = document.pk
        kb_pk = kb.pk

    if reindex:
        kb_payload = reindex_assistant_kb(kb_pk, wait=True)
        document = AssistantKnowledgeBaseDocument.objects.get(pk=document_id)
        return {
            "knowledge_base": kb_payload,
            "document": serialize_document(document),
        }

    kb = AssistantKnowledgeBase.objects.get(pk=kb_pk)
    document = AssistantKnowledgeBaseDocument.objects.get(pk=document_id)
    return {
        "knowledge_base": serialize_kb(kb, include_documents=True),
        "document": serialize_document(document),
    }


def delete_assistant_document(kb_id: int, document_id: int) -> dict[str, Any]:
    with transaction.atomic():
        try:
            kb = AssistantKnowledgeBase.objects.select_for_update().get(pk=kb_id)
        except AssistantKnowledgeBase.DoesNotExist as exc:
            raise AssistantAdminError("KB not found") from exc
        try:
            document = kb.documents.get(pk=document_id)
        except AssistantKnowledgeBaseDocument.DoesNotExist as exc:
            raise AssistantAdminError("document not found") from exc
        AssistantProductionChunk.objects.filter(
            kb_slug=kb.slug,
            article_id=document.article_id,
        ).delete()
        delete_assistant_original(document)
        document.delete()
        kb.document_count = kb.documents.count()
        kb.chunk_count = AssistantProductionChunk.objects.filter(
            kb_slug=kb.slug,
            is_active=True,
        ).count()
        kb.status_message = "Документ удалён"
        if kb.status == AssistantKnowledgeBase.STATUS_INDEXING:
            kb.status = AssistantKnowledgeBase.STATUS_IDLE
        kb.save(
            update_fields=(
                "document_count",
                "chunk_count",
                "status",
                "status_message",
                "updated_at",
            )
        )
        return serialize_kb(kb, include_documents=True)


def reindex_assistant_kb(kb_id: int, *, wait: bool = False) -> dict[str, Any]:
    try:
        kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
    except AssistantKnowledgeBase.DoesNotExist as exc:
        raise AssistantAdminError("KB not found") from exc
    if not kb.slug.startswith(ASSISTANT_SLUG_PREFIX):
        raise AssistantAdminError("refusing to index non-assistant namespace")

    kb.status = AssistantKnowledgeBase.STATUS_INDEXING
    kb.status_message = "Индексация выполняется"
    kb.save(update_fields=("status", "status_message", "updated_at"))
    for document in kb.documents.exclude(
        status=AssistantKnowledgeBaseDocument.STATUS_ERROR
    ):
        document.status = AssistantKnowledgeBaseDocument.STATUS_UPLOADED
        document.save(update_fields=("status",))
        write_index_progress(document, 0)

    if wait:
        _run_assistant_reindex(kb_id)
        return get_assistant_kb(kb_id)

    from hub.kb_admin import _spawn_reindex

    _spawn_reindex(
        lambda: _run_assistant_reindex(kb_id),
        name=f"assistant-reindex-{kb_id}",
    )
    return get_assistant_kb(kb_id)


_POLICY_TITLES = {
    "113.1": "Положение о материальной помощи",
    "20.10": "Положение о матпомощи на строительство жилья",
    "54.2": "Положение о профессиональном тестировании",
    "55.3": "Положение о премировании",
    "94.4": "Положение о рабочем времени и отпусках",
    "136.6": "Положение об аттестации работников",
    "137.5": "Положение об обучении работников",
    "141.8": "Положение о подборе и адаптации персонала",
    "176.3": "Положение об оплате труда",
    "28.9": "Положение о служебных командировках",
}


def _display_document_title(kb: AssistantKnowledgeBase, document: AssistantKnowledgeBaseDocument) -> str:
    """Card title. Numeric filenames like 141.8.doc are not shown to the operator."""
    stem = Path(str(document.filename or "")).stem.strip()
    for key, title in _POLICY_TITLES.items():
        if stem == key or stem.startswith(f"{key} ") or stem.startswith(f"{key}.") or key in stem:
            return title
    if re.fullmatch(r"\d+(?:\.\d+)?", stem):
        return (kb.name or stem).strip() or stem
    return stem or (kb.name or "").strip() or "Документ"


def _run_assistant_reindex(kb_id: int) -> None:
    kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
    chunk_size, overlap, embedding_model = _chunk_profile()
    total_chunks = 0
    try:
        documents = list(kb.documents.order_by("pk"))
        for document in documents:
            text = normalize_text(document.extracted_text)
            if not text:
                document.status = AssistantKnowledgeBaseDocument.STATUS_ERROR
                document.status_message = "Нет текста для индексации"
                document.chunk_count = 0
                document.save(
                    update_fields=(
                        "status",
                        "status_message",
                        "chunk_count",
                    )
                )
                continue
            chunks = chunk_text(
                text,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            write_index_progress(document, 5)
            kb.status_message = f"Индексация «{document.filename}» 5%"
            kb.save(update_fields=("status_message", "updated_at"))
            checksum = checksum_for_text(text)
            batch = 8
            vectors: list[list[float]] = []
            for start in range(0, len(chunks), batch):
                part = chunks[start : start + batch]
                vectors.extend(embed_texts(part, is_query=False))
                done = start + len(part)
                percent = min(99, max(5, round(100 * done / len(chunks))))
                write_index_progress(document, percent)
                kb.status_message = (
                    f"Индексация «{document.filename}» {percent}%"
                )
                kb.save(update_fields=("status_message", "updated_at"))
            with transaction.atomic():
                AssistantProductionChunk.objects.filter(
                    kb_slug=kb.slug,
                    article_id=document.article_id,
                ).delete()
                AssistantProductionChunk.objects.bulk_create(
                    [
                        AssistantProductionChunk(
                            kb_slug=kb.slug,
                            article_id=document.article_id,
                            version_id=document.pk,
                            chunk_index=index,
                            title=_display_document_title(kb, document),
                            content=chunk,
                            permalink=assistant_source_download_url(
                                kb_slug=kb.slug,
                                article_id=document.article_id,
                            ),
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
                document.status = AssistantKnowledgeBaseDocument.STATUS_INDEXED
                document.status_message = ""
                document.chunk_count = len(chunks)
                document.indexed_at = timezone.now()
                document.save(
                    update_fields=(
                        "status",
                        "status_message",
                        "chunk_count",
                        "indexed_at",
                    )
                )
            total_chunks += len(chunks)
        kb.status = AssistantKnowledgeBase.STATUS_READY
        kb.status_message = "Индекс актуален"
        kb.chunk_count = total_chunks
        kb.document_count = kb.documents.count()
        kb.last_reindexed_at = timezone.now()
        kb.save(
            update_fields=(
                "status",
                "status_message",
                "chunk_count",
                "document_count",
                "last_reindexed_at",
                "updated_at",
            )
        )
    except Exception as exc:
        kb.status = AssistantKnowledgeBase.STATUS_ERROR
        kb.status_message = str(exc)[:500]
        kb.save(update_fields=("status", "status_message", "updated_at"))
        raise AssistantAdminError(kb.status_message) from exc


def list_prompts() -> list[dict[str, Any]]:
    ensure_assistant_seed()
    return [
        serialize_prompt(item)
        for item in AssistantPromptTemplate.objects.all()
    ]


def get_prompt(prompt_id: int) -> dict[str, Any]:
    try:
        return serialize_prompt(AssistantPromptTemplate.objects.get(pk=prompt_id))
    except AssistantPromptTemplate.DoesNotExist as exc:
        raise AssistantAdminError("prompt not found") from exc


def create_prompt(
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    body = str(payload.get("body") or "").strip()
    if not name or not body:
        raise AssistantAdminError("name and body are required")
    prompt_type = str(payload.get("prompt_type") or "task")
    if prompt_type not in {
        AssistantPromptTemplate.TYPE_SYSTEM,
        AssistantPromptTemplate.TYPE_TASK,
        AssistantPromptTemplate.TYPE_SCOPE,
    }:
        raise AssistantAdminError("prompt_type must be system|task|scope")
    kb_slug = str(payload.get("kb_slug") or "").strip()
    if kb_slug:
        kb_slug = _normalize_assistant_slug(kb_slug)
    prompt = AssistantPromptTemplate.objects.create(
        name=name,
        prompt_type=prompt_type,
        scope=str(payload.get("scope") or "bank")[:64],
        event_trigger=str(payload.get("event_trigger") or "")[:128],
        body=body,
        status=AssistantPromptTemplate.STATUS_DRAFT,
        kb_slug=kb_slug,
        updated_by=username,
    )
    return serialize_prompt(prompt)


def update_prompt(
    prompt_id: int,
    payload: Mapping[str, Any],
    *,
    username: str,
) -> dict[str, Any]:
    try:
        prompt = AssistantPromptTemplate.objects.get(pk=prompt_id)
    except AssistantPromptTemplate.DoesNotExist as exc:
        raise AssistantAdminError("prompt not found") from exc

    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise AssistantAdminError("name cannot be empty")
        prompt.name = name
    if "body" in payload:
        body = str(payload.get("body") or "").strip()
        if not body:
            raise AssistantAdminError("body cannot be empty")
        prompt.body = body
    if "prompt_type" in payload:
        prompt_type = str(payload.get("prompt_type") or "")
        if prompt_type not in {
            AssistantPromptTemplate.TYPE_SYSTEM,
            AssistantPromptTemplate.TYPE_TASK,
            AssistantPromptTemplate.TYPE_SCOPE,
        }:
            raise AssistantAdminError("prompt_type must be system|task|scope")
        prompt.prompt_type = prompt_type
    if "scope" in payload:
        prompt.scope = str(payload.get("scope") or "bank")[:64]
    if "event_trigger" in payload:
        prompt.event_trigger = str(payload.get("event_trigger") or "")[:128]
    if "kb_slug" in payload:
        kb_slug = str(payload.get("kb_slug") or "").strip()
        prompt.kb_slug = _normalize_assistant_slug(kb_slug) if kb_slug else ""
    if "status" in payload:
        status = str(payload.get("status") or "")
        if status not in {
            AssistantPromptTemplate.STATUS_DRAFT,
            AssistantPromptTemplate.STATUS_PUBLISHED,
        }:
            raise AssistantAdminError("status must be draft|published")
        if (
            status == AssistantPromptTemplate.STATUS_PUBLISHED
            and prompt.status != AssistantPromptTemplate.STATUS_PUBLISHED
        ):
            prompt.version += 1
        prompt.status = status

    prompt.updated_by = username
    prompt.save()
    return serialize_prompt(prompt)


def delete_prompt(prompt_id: int) -> None:
    deleted, _ = AssistantPromptTemplate.objects.filter(pk=prompt_id).delete()
    if not deleted:
        raise AssistantAdminError("prompt not found")


def list_capabilities() -> list[dict[str, Any]]:
    ensure_assistant_seed()
    return [
        serialize_capability(item)
        for item in AssistantCapability.objects.all()
    ]


@transaction.atomic
def update_capability(
    code: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    ensure_assistant_seed()
    try:
        item = AssistantCapability.objects.select_for_update().get(code=code)
    except AssistantCapability.DoesNotExist as exc:
        raise AssistantAdminError("capability not found") from exc
    if "enabled" in payload:
        if not isinstance(payload.get("enabled"), bool):
            raise AssistantAdminError("enabled must be a boolean")
        item.enabled = bool(payload["enabled"])
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if name:
            item.name = name
    if "description" in payload:
        item.description = str(payload.get("description") or "")
    item.save()
    return serialize_capability(item)
