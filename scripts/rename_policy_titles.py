"""Point indexed policy cards at human titles without re-embedding."""
from __future__ import annotations

import os
from pathlib import Path

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")
django.setup()

from hub.assistant_admin import _display_document_title  # noqa: E402
from hub.models import AssistantKnowledgeBaseDocument  # noqa: E402
from ingest.models import AssistantProductionChunk  # noqa: E402

for document in AssistantKnowledgeBaseDocument.objects.select_related("knowledge_base"):
    title = _display_document_title(document.knowledge_base, document)
    stem = Path(document.filename or "").stem
    if title == stem:
        print("KEEP", document.filename)
        continue
    updated = AssistantProductionChunk.objects.filter(
        kb_slug=document.knowledge_base.slug,
        article_id=document.article_id,
    ).update(title=title)
    suffix = Path(document.filename or "").suffix or ".doc"
    document.filename = f"{title}{suffix}"
    document.save(update_fields=("filename",))
    print(f"RENAMED {stem} -> {title} chunks={updated}")
print("TITLES_DONE")
