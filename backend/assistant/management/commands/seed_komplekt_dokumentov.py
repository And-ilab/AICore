"""Seed the Belarusbank physical-person document-pack memo as a separate assistant KB."""

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

KB_SLUG = "assistant_komplekt_dokumentov"
KB_NAME = "Комплект документов для физлиц"
FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "hub"
    / "fixtures"
    / "komplekt-dokumentov-fizicheskih-lic.txt"
)


class Command(BaseCommand):
    help = "Create KB «Комплект документов для физлиц» and index the memo"

    def handle(self, *args, **options):
        if not FIXTURE.is_file():
            raise SystemExit(f"fixture not found: {FIXTURE}")
        existing = AssistantKnowledgeBase.objects.filter(slug=KB_SLUG).first()
        if existing is None:
            payload = create_assistant_kb(
                {
                    "name": KB_NAME,
                    "slug": KB_SLUG,
                    "description": "Какие документы нужны для операций физлица в Беларусбанке",
                },
                username="seed_komplekt_dokumentov",
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
                username="seed_komplekt_dokumentov",
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
