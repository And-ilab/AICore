"""Seed KB «Сроки действия справок» with the credit-certificate memo."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from hub.assistant_admin import (
    create_assistant_kb,
    reindex_assistant_kb,
    serialize_document,
    upload_assistant_document,
)
from hub.models import AssistantKnowledgeBase

KB_SLUG = "assistant_sroki_spravok"
KB_NAME = "Кредитование"
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "hub"
    / "fixtures"
    / "sroki-deystviya-spravok.txt"
)


class Command(BaseCommand):
    help = "Create KB «Кредитование» and index the memo"

    def handle(self, *args, **options):
        if not FIXTURE.is_file():
            raise SystemExit(f"fixture not found: {FIXTURE}")
        existing = AssistantKnowledgeBase.objects.filter(slug=KB_SLUG).first()
        if existing is None:
            payload = create_assistant_kb(
                {
                    "name": KB_NAME,
                    "slug": KB_SLUG,
                    "description": "Кредитные продукты для физических лиц",
                },
                username="seed_sroki_spravok",
            )
            kb_id = int(payload["id"])
            self.stdout.write(f"Created KB {KB_SLUG} id={kb_id}")
        else:
            kb_id = existing.pk
            self.stdout.write(f"Using existing KB {KB_SLUG} id={kb_id}")
        kb = AssistantKnowledgeBase.objects.get(pk=kb_id)
        already = kb.documents.filter(filename=FIXTURE.name).first()
        if already is None:
            result = upload_assistant_document(
                kb_id,
                filename=FIXTURE.name,
                content_type="text/plain; charset=utf-8",
                data=FIXTURE.read_bytes(),
                username="seed_sroki_spravok",
                reindex=True,
            )
        else:
            kb_payload = reindex_assistant_kb(kb_id)
            result = {
                "knowledge_base": kb_payload,
                "document": serialize_document(already),
            }
            self.stdout.write("Document already attached, reindexed")
        kb_out = result.get("knowledge_base") or {}
        doc = result.get("document") or {}
        self.stdout.write(
            self.style.SUCCESS(
                f"{kb_out.get('name')} slug={kb_out.get('slug')} "
                f"docs={kb_out.get('document_count')} chunks={kb_out.get('chunk_count')} "
                f"file={doc.get('filename')} status={doc.get('status')}"
            )
        )
