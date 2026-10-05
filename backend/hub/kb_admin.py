"""No-code contact-center knowledge-base management (FR-CC-08 / FR-CC-13)."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import BadZipFile

from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from django.utils.text import slugify

from core.model_registry import ModelRegistry
from core.text_language import safe_ru_en_text
from hub.models import ContactCenterKnowledgeBase, KnowledgeBaseDocument
from core.embeddings import embed_passage
from ingest.pipeline import (
    checksum_for_text,
    chunk_text,
    normalize_text,
)
from ingest.models import CCProductionChunk, KnowledgeIngestEvent, SuzReconcileState

ARTICLE_ID_BASE = 2_000_000_000
SUZ_KB_SLUG = "suz-bitrix"
SUZ_KB_NAME = "СУЗ Битрикс"
SOURCE_LABELS = {
    ContactCenterKnowledgeBase.SOURCE_MANUAL: "Ручная загрузка",
    ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX: "СУЗ Битрикс",
}
ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".txt",
        ".rtf",
        ".xlsx",
        ".pptx",
        ".png",
        ".jpg",
        ".jpeg",
    }
)
TEXT_EXTENSIONS = frozenset({".txt", ".rtf"})
WHITESPACE = re.compile(r"\s+")
_PROGRESS_RE = re.compile(r"(\d+)\s*%")
WORD_NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
}


class KnowledgeBaseError(ValueError):
    """Raised for invalid KB admin operations."""


def _unique_slug(name: str) -> str:
    base = slugify(name, allow_unicode=False) or "kb"
    candidate = base
    index = 2
    while ContactCenterKnowledgeBase.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _source_label(source: str) -> str:
    return SOURCE_LABELS.get(source, source)


def document_index_percent(status: str, status_message: str = "") -> int:
    """100 when indexed; live 0–99 from «Индексация 42%» while running."""
    if status == "indexed":
        return 100
    if status == "error":
        return 0
    match = _PROGRESS_RE.search(status_message or "")
    if match:
        return max(0, min(99, int(match.group(1))))
    return 0


def _document_index_percent(status: str, status_message: str = "") -> int:
    return document_index_percent(status, status_message)


def _index_percent_from_docs(documents: list[dict[str, Any]]) -> int:
    if not documents:
        return 0
    total = sum(
        int(doc.get("index_percent") or 0)
        if "index_percent" in doc
        else _document_index_percent(
            str(doc.get("status") or ""),
            str(doc.get("status_message") or ""),
        )
        for doc in documents
    )
    return round(total / len(documents))


def _index_percent_from_statuses(statuses: list[str]) -> int:
    if not statuses:
        return 0
    total = sum(_document_index_percent(status) for status in statuses)
    return round(total / len(statuses))


def write_index_progress(document: Any, percent: int) -> None:
    """Persist a live percent on the document without flipping it to indexed."""
    value = max(0, min(99, int(percent)))
    document.status_message = f"Индексация {value}%"
    document.save(update_fields=("status_message",))


def webhook_suz_status() -> dict[str, str]:
    """Global Bitrix SUZ webhook / reconcile health for the unified KB UI."""
    state = SuzReconcileState.objects.filter(pk=1).first()
    if state and state.last_error:
        return {"status": "ERROR", "label": "ERROR"}
    last_event = KnowledgeIngestEvent.objects.order_by("-received_at").first()
    if last_event is not None or (state and state.last_run_at):
        return {"status": "OK", "label": "OK"}
    return {"status": "IDLE", "label": "—"}


def _suz_article_rows() -> list[dict[str, Any]]:
    """Active Bitrix articles in cc_production (article_id below admin range)."""
    rows = (
        CCProductionChunk.objects.filter(
            is_active=True,
            article_id__lt=ARTICLE_ID_BASE,
        )
        .values("article_id")
        .annotate(
            chunk_count=Count("id"),
            title=Max("title"),
            permalink=Max("permalink"),
            indexed_at=Max("indexed_at"),
        )
        .order_by("article_id")
    )
    documents: list[dict[str, Any]] = []
    for row in rows:
        title = (row["title"] or f"Статья {row['article_id']}").strip()
        documents.append(
            {
                "id": int(row["article_id"]),
                "filename": title,
                "content_type": "suz/bitrix",
                "size_bytes": 0,
                "status": KnowledgeBaseDocument.STATUS_INDEXED,
                "status_message": "",
                "chunk_count": int(row["chunk_count"] or 0),
                "index_percent": 100,
                "source": ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX,
                "source_label": _source_label(
                    ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX
                ),
                "readonly": True,
                "uploaded_at": (
                    row["indexed_at"].isoformat() if row["indexed_at"] else ""
                ),
                "indexed_at": (
                    row["indexed_at"].isoformat() if row["indexed_at"] else None
                ),
                "uploaded_by": "suz_bitrix",
                "permalink": row["permalink"] or "",
            }
        )
    return documents


def sync_suz_knowledge_base(
    kb: ContactCenterKnowledgeBase | None = None,
) -> ContactCenterKnowledgeBase:
    """Ensure the system SUZ KB exists and mirrors cc_production article stats."""
    if kb is None:
        kb, _ = ContactCenterKnowledgeBase.objects.get_or_create(
            slug=SUZ_KB_SLUG,
            defaults={
                "name": SUZ_KB_NAME,
                "scope": "contact_center",
                "description": (
                    "Статьи из интеграции СУЗ Битрикс (webhook / reconcile)"
                ),
                "source": ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX,
                "status": ContactCenterKnowledgeBase.STATUS_READY,
                "status_message": "Индекс синхронизируется через webhook СУЗ",
                "created_by": "system",
            },
        )
    if kb.source != ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX:
        kb.source = ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX
    docs = _suz_article_rows()
    chunk_count = sum(item["chunk_count"] for item in docs)
    kb.name = SUZ_KB_NAME
    kb.document_count = len(docs)
    kb.chunk_count = chunk_count
    if docs:
        kb.status = ContactCenterKnowledgeBase.STATUS_READY
        kb.status_message = "Индекс актуален (СУЗ Битрикс)"
    else:
        kb.status = ContactCenterKnowledgeBase.STATUS_IDLE
        kb.status_message = "Ожидание статей из webhook СУЗ"
    webhook = webhook_suz_status()
    if webhook["status"] == "ERROR":
        kb.status = ContactCenterKnowledgeBase.STATUS_ERROR
        kb.status_message = "Ошибка webhook / reconcile СУЗ"
    kb.save(
        update_fields=(
            "name",
            "source",
            "document_count",
            "chunk_count",
            "status",
            "status_message",
            "updated_at",
        )
    )
    return kb


def ensure_suz_knowledge_base() -> ContactCenterKnowledgeBase:
    return sync_suz_knowledge_base()


def serialize_document(
    document: KnowledgeBaseDocument,
    *,
    source: str = ContactCenterKnowledgeBase.SOURCE_MANUAL,
) -> dict[str, Any]:
    return {
        "id": document.pk,
        "filename": document.filename,
        "content_type": document.content_type,
        "size_bytes": document.size_bytes,
        "status": document.status,
        "status_message": document.status_message,
        "chunk_count": document.chunk_count,
        "index_percent": _document_index_percent(
            document.status, document.status_message
        ),
        "source": source,
        "source_label": _source_label(source),
        "readonly": source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX,
        "uploaded_at": document.uploaded_at.isoformat(),
        "indexed_at": (
            document.indexed_at.isoformat() if document.indexed_at else None
        ),
        "uploaded_by": document.uploaded_by,
    }


def serialize_knowledge_base(
    kb: ContactCenterKnowledgeBase,
    *,
    include_documents: bool = False,
) -> dict[str, Any]:
    source = kb.source or ContactCenterKnowledgeBase.SOURCE_MANUAL
    is_suz = source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX
    documents: list[dict[str, Any]]
    if include_documents:
        if is_suz:
            documents = _suz_article_rows()
        else:
            documents = [
                serialize_document(document, source=source)
                for document in kb.documents.all()
            ]
    else:
        documents = []

    if is_suz and not include_documents:
        index_percent = 100 if kb.document_count else 0
        if kb.status == ContactCenterKnowledgeBase.STATUS_ERROR:
            index_percent = 0
    elif include_documents:
        index_percent = _index_percent_from_docs(documents)
    else:
        indexed = kb.documents.filter(
            status=KnowledgeBaseDocument.STATUS_INDEXED
        ).count()
        total = kb.document_count or kb.documents.count()
        index_percent = round(100 * indexed / total) if total else 0
        if kb.status == ContactCenterKnowledgeBase.STATUS_INDEXING and total:
            index_percent = min(index_percent, 99) if index_percent else 0

    webhook = webhook_suz_status()
    payload: dict[str, Any] = {
        "id": kb.pk,
        "name": kb.name,
        "slug": kb.slug,
        "scope": kb.scope,
        "description": kb.description,
        "source": source,
        "source_label": _source_label(source),
        "status": kb.status,
        "status_message": kb.status_message,
        "document_count": (
            len(documents) if include_documents and is_suz else kb.document_count
        ),
        "chunk_count": (
            sum(doc["chunk_count"] for doc in documents)
            if include_documents and is_suz
            else kb.chunk_count
        ),
        "index_percent": index_percent,
        "webhook_status": webhook["status"],
        "webhook_label": webhook["label"],
        "readonly": is_suz,
        "last_reindexed_at": (
            kb.last_reindexed_at.isoformat() if kb.last_reindexed_at else None
        ),
        "created_at": kb.created_at.isoformat(),
        "updated_at": kb.updated_at.isoformat(),
        "created_by": kb.created_by,
    }
    if include_documents:
        payload["documents"] = documents
    return payload


def list_knowledge_bases() -> list[dict[str, Any]]:
    ensure_suz_knowledge_base()
    return [
        serialize_knowledge_base(kb)
        for kb in ContactCenterKnowledgeBase.objects.all()
    ]


def get_knowledge_base(kb_id: int) -> dict[str, Any]:
    kb = ContactCenterKnowledgeBase.objects.prefetch_related("documents").get(
        pk=kb_id
    )
    if kb.source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX or (
        kb.slug == SUZ_KB_SLUG
    ):
        kb = sync_suz_knowledge_base(kb)
    return serialize_knowledge_base(kb, include_documents=True)


@transaction.atomic
def create_knowledge_base(
    *,
    name: str,
    scope: str = "contact_center",
    description: str = "",
    username: str = "",
) -> dict[str, Any]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise KnowledgeBaseError("name must be a non-empty string")
    if cleaned_name.lower() == SUZ_KB_NAME.lower():
        raise KnowledgeBaseError(
            "name «СУЗ Битрикс» зарезервировано для интеграции"
        )
    if ContactCenterKnowledgeBase.objects.filter(name__iexact=cleaned_name).exists():
        raise KnowledgeBaseError("knowledge base with this name already exists")
    kb = ContactCenterKnowledgeBase.objects.create(
        name=cleaned_name,
        slug=_unique_slug(cleaned_name),
        scope=(scope or "contact_center").strip() or "contact_center",
        description=description.strip(),
        source=ContactCenterKnowledgeBase.SOURCE_MANUAL,
        status=ContactCenterKnowledgeBase.STATUS_IDLE,
        created_by=username,
    )
    return serialize_knowledge_base(kb, include_documents=True)


def _require_manual_kb(kb: ContactCenterKnowledgeBase) -> None:
    if (
        kb.source == ContactCenterKnowledgeBase.SOURCE_SUZ_BITRIX
        or kb.slug == SUZ_KB_SLUG
    ):
        raise KnowledgeBaseError(
            "База СУЗ Битрикс управляется через webhook; "
            "ручная загрузка и удаление недоступны"
        )


@transaction.atomic
def delete_knowledge_base(kb_id: int) -> None:
    kb = ContactCenterKnowledgeBase.objects.get(pk=kb_id)
    _require_manual_kb(kb)
    article_ids = list(kb.documents.values_list("article_id", flat=True))
    if article_ids:
        CCProductionChunk.objects.filter(article_id__in=article_ids).delete()
    kb.delete()


def _extract_docx_text(data: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            xml_bytes = archive.read("word/document.xml")
    except (BadZipFile, KeyError) as exc:
        raise KnowledgeBaseError("invalid docx file") from exc
    root = ET.fromstring(xml_bytes)
    parts = [
        node.text or ""
        for node in root.findall(".//w:t", WORD_NS)
        if node.text
    ]
    text = normalize_text(" ".join(parts))
    if not text:
        raise KnowledgeBaseError("docx file contains no extractable text")
    return text


def _extract_doc_text(filename: str, data: bytes) -> str:
    """Extract Word 97–2003 through antiword; never decode OLE bytes directly."""
    executable = shutil.which("antiword")
    if not executable:
        raise KnowledgeBaseError(
            "Для обработки .doc на сервере не установлен antiword. "
            "Обратитесь к администратору или загрузите DOCX."
        )
    suffix = Path(filename).suffix or ".doc"
    temporary_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            temporary.write(data)
            temporary_path = temporary.name
        completed = subprocess.run(
            [executable, "-w", "0", temporary_path],
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise KnowledgeBaseError("Не удалось извлечь текст из .doc.") from exc
    finally:
        if temporary_path:
            Path(temporary_path).unlink(missing_ok=True)
    if completed.returncode != 0 or not completed.stdout:
        details = completed.stderr.decode("utf-8", errors="ignore").strip()
        raise KnowledgeBaseError(
            f"Файл .doc повреждён или не поддерживается antiword: {details}"
        )
    try:
        decoded = completed.stdout.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded = completed.stdout.decode("cp1251")
        except UnicodeDecodeError as exc:
            raise KnowledgeBaseError(
                "antiword вернул текст в неизвестной кодировке."
            ) from exc
    text = normalize_text(decoded)
    if not text:
        raise KnowledgeBaseError("Файл .doc не содержит извлекаемого текста.")
    return _validate_extracted_text(text)


def _extract_xlsx_text(data: bytes) -> str:
    """Read cell values from an XLSX workbook (shared strings + inline)."""
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            names = set(archive.namelist())
            shared: list[str] = []
            if "xl/sharedStrings.xml" in names:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for item in root.findall("m:si", ns):
                    bits = [node.text or "" for node in item.findall(".//m:t", ns)]
                    shared.append("".join(bits))
            sheets = sorted(
                name
                for name in names
                if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
            )
            if not sheets:
                raise KnowledgeBaseError("xlsx file contains no worksheets")
            lines: list[str] = []
            for sheet_name in sheets:
                sheet = ET.fromstring(archive.read(sheet_name))
                ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for row in sheet.findall(".//m:row", ns):
                    values: list[str] = []
                    for cell in row.findall("m:c", ns):
                        value_node = cell.find("m:v", ns)
                        if value_node is None or value_node.text is None:
                            continue
                        raw = value_node.text
                        if cell.get("t") == "s":
                            try:
                                raw = shared[int(raw)]
                            except (ValueError, IndexError):
                                pass
                        if str(raw).strip():
                            values.append(str(raw).strip())
                    if values:
                        lines.append(" | ".join(values))
    except (BadZipFile, KeyError, ET.ParseError) as exc:
        raise KnowledgeBaseError("invalid xlsx file") from exc
    text = "\n".join(lines).strip()
    if not text:
        raise KnowledgeBaseError("xlsx file contains no extractable text")
    return text


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        PdfReader = None  # type: ignore[misc, assignment]
    if PdfReader is not None:
        reader = PdfReader(BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = normalize_text("\n".join(pages))
        if text:
            return text
    raise KnowledgeBaseError(
        "PDF не содержит извлекаемого текста. Выполните OCR или загрузите DOCX/TXT."
    )


def _validate_extracted_text(text: str) -> str:
    safe = safe_ru_en_text(normalize_text(text))
    if not safe:
        raise KnowledgeBaseError(
            "Документ содержит повреждённый текст или символы вне русского "
            "и английского алфавитов. Пересохраните исходник как DOCX/PDF."
        )
    return safe


def extract_document_text(filename: str, data: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise KnowledgeBaseError(f"unsupported file type; allowed: {allowed}")
    if not data:
        raise KnowledgeBaseError("uploaded file is empty")
    if extension in TEXT_EXTENSIONS:
        try:
            decoded = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise KnowledgeBaseError(
                "Текстовый файл должен быть сохранён в UTF-8."
            ) from exc
        text = normalize_text(decoded)
        if not text:
            raise KnowledgeBaseError("text file is empty")
        return _validate_extracted_text(text)
    if extension == ".docx":
        return _validate_extracted_text(_extract_docx_text(data))
    if extension == ".doc":
        return _extract_doc_text(filename, data)
    if extension == ".pdf":
        return _validate_extracted_text(_extract_pdf_text(data))
    if extension == ".xlsx":
        return _validate_extracted_text(_extract_xlsx_text(data))
    # Binary office/image formats: keep a searchable filename marker for MVP.
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    return _validate_extracted_text(normalize_text(f"{stem} {filename}"))


@transaction.atomic
def upload_document(
    kb_id: int,
    *,
    filename: str,
    content_type: str,
    data: bytes,
    username: str = "",
    reindex: bool = True,
) -> dict[str, Any]:
    kb = ContactCenterKnowledgeBase.objects.select_for_update().get(pk=kb_id)
    _require_manual_kb(kb)
    cleaned_name = Path(filename).name.strip()
    if not cleaned_name:
        raise KnowledgeBaseError("filename is required")
    text = extract_document_text(cleaned_name, data)
    # Temporary unique article_id until PK is known.
    provisional_article_id = ARTICLE_ID_BASE + (
        KnowledgeBaseDocument.objects.count() + 1
    ) * 10_000 + (kb.pk % 10_000)
    while KnowledgeBaseDocument.objects.filter(
        article_id=provisional_article_id
    ).exists():
        provisional_article_id += 1
    document = KnowledgeBaseDocument.objects.create(
        knowledge_base=kb,
        filename=cleaned_name,
        content_type=content_type or "",
        size_bytes=len(data),
        status=KnowledgeBaseDocument.STATUS_UPLOADED,
        extracted_text=text,
        uploaded_by=username,
        article_id=provisional_article_id,
    )
    document.article_id = ARTICLE_ID_BASE + document.pk
    document.save(update_fields=("article_id",))
    kb.document_count = kb.documents.count()
    kb.status = ContactCenterKnowledgeBase.STATUS_IDLE
    kb.status_message = "Документ загружен, требуется переиндексация"
    kb.save(
        update_fields=(
            "document_count",
            "status",
            "status_message",
            "updated_at",
        )
    )
    if reindex:
        reindex_knowledge_base(kb.pk, wait=True)
        kb.refresh_from_db()
        document.refresh_from_db()
    return {
        "knowledge_base": serialize_knowledge_base(kb, include_documents=True),
        "document": serialize_document(document),
    }


@transaction.atomic
def delete_document(kb_id: int, document_id: int) -> dict[str, Any]:
    kb = ContactCenterKnowledgeBase.objects.select_for_update().get(pk=kb_id)
    _require_manual_kb(kb)
    document = kb.documents.get(pk=document_id)
    CCProductionChunk.objects.filter(article_id=document.article_id).delete()
    document.delete()
    kb.document_count = kb.documents.count()
    kb.chunk_count = sum(kb.documents.values_list("chunk_count", flat=True))
    kb.status_message = "Документ удалён"
    kb.save(
        update_fields=(
            "document_count",
            "chunk_count",
            "status_message",
            "updated_at",
        )
    )
    return serialize_knowledge_base(kb, include_documents=True)


def reindex_knowledge_base(kb_id: int, *, wait: bool = True) -> dict[str, Any]:
    kb = ContactCenterKnowledgeBase.objects.get(pk=kb_id)
    _require_manual_kb(kb)
    kb.status = ContactCenterKnowledgeBase.STATUS_INDEXING
    kb.status_message = "Индексация выполняется"
    kb.save(update_fields=("status", "status_message", "updated_at"))
    if not wait:
        _spawn_reindex(lambda: _run_cc_reindex(kb_id), name=f"cc-reindex-{kb_id}")
        return serialize_knowledge_base(kb, include_documents=True)
    _run_cc_reindex(kb_id)
    kb.refresh_from_db()
    return serialize_knowledge_base(kb, include_documents=True)


def _spawn_reindex(job, *, name: str) -> None:
    import threading

    from django.db import close_old_connections

    def runner() -> None:
        close_old_connections()
        try:
            job()
        finally:
            close_old_connections()

    threading.Thread(target=runner, daemon=True, name=name).start()


def _run_cc_reindex(kb_id: int) -> None:
    kb = ContactCenterKnowledgeBase.objects.get(pk=kb_id)
    _require_manual_kb(kb)
    registry = ModelRegistry.load()
    profile = registry.get_profile("kb_cc_production")
    total_chunks = 0
    try:
        for document in kb.documents.order_by("pk"):
            text = normalize_text(document.extracted_text)
            if not text:
                document.status = KnowledgeBaseDocument.STATUS_ERROR
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
                chunk_size=profile.chunk_size_tokens,
                overlap=profile.chunk_overlap_tokens,
            )
            write_index_progress(document, 5)
            kb.status_message = f"Индексация «{document.filename}» 5%"
            kb.save(update_fields=("status_message", "updated_at"))
            checksum = checksum_for_text(text)
            # Prefer a real source URL from the document body when present
            # (e.g. scraper "URL: https://belarusbank.by/..."), else local stub.
            source_url = ""
            for line in text.splitlines()[:12]:
                stripped = line.strip()
                if stripped.lower().startswith("url:"):
                    candidate = stripped.split(":", 1)[1].strip()
                    if candidate.startswith("http://") or candidate.startswith("https://"):
                        source_url = candidate
                        break
                if stripped.startswith("http://") or stripped.startswith("https://"):
                    source_url = stripped.split()[0]
                    break
            permalink = source_url or (
                f"https://suz.local/admin-kb/{kb.slug}/documents/{document.pk}"
            )
            step = max(1, len(chunks) // 20)
            embeddings: list[list[float]] = []
            for index, chunk in enumerate(chunks):
                embeddings.append(embed_passage(chunk))
                if index == 0 or (index + 1) % step == 0 or index + 1 == len(chunks):
                    percent = min(99, max(5, round(100 * (index + 1) / len(chunks))))
                    write_index_progress(document, percent)
                    kb.status_message = (
                        f"Индексация «{document.filename}» {percent}%"
                    )
                    kb.save(update_fields=("status_message", "updated_at"))
            with transaction.atomic():
                CCProductionChunk.objects.filter(
                    article_id=document.article_id
                ).delete()
                CCProductionChunk.objects.bulk_create(
                    [
                        CCProductionChunk(
                            article_id=document.article_id,
                            version_id=document.pk,
                            chunk_index=index,
                            title=document.filename,
                            content=chunk,
                            permalink=permalink,
                            locale="ru",
                            visibility_scope=["kc_operator", "contact_center"],
                            checksum=checksum,
                            embedding_model=profile.embedding_model,
                            embedding=embeddings[index],
                            is_active=True,
                        )
                        for index, chunk in enumerate(chunks)
                    ]
                )
                document.status = KnowledgeBaseDocument.STATUS_INDEXED
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
        kb.status = ContactCenterKnowledgeBase.STATUS_READY
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
    except KnowledgeBaseError:
        kb.status = ContactCenterKnowledgeBase.STATUS_ERROR
        kb.save(update_fields=("status", "updated_at"))
        raise
    except ValueError as exc:
        kb.status = ContactCenterKnowledgeBase.STATUS_ERROR
        kb.status_message = str(exc)[:500]
        kb.save(update_fields=("status", "status_message", "updated_at"))
        raise KnowledgeBaseError(kb.status_message) from exc

    return serialize_knowledge_base(kb, include_documents=True)
