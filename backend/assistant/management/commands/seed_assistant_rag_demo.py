"""Seed a demo assistant KB document and reindex for local RAG smoke tests."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from hub.assistant_admin import (
    create_assistant_kb,
    list_assistant_kbs,
    reindex_assistant_kb,
    upload_assistant_document,
)
from hub.models import AssistantKnowledgeBase

DEMO_SLUG = "assistant_hr"
DEMO_FILENAME = "hr-vacation-policy.txt"
DEMO_TEXT = """Регламент отпусков HR-12

Сотрудник банка имеет право на ежегодный оплачиваемый отпуск продолжительностью
28 календарных дней.

Заявление на отпуск подаётся в HR-портале не позднее чем за 14 календарных дней
до даты начала отпуска. Согласование руководителя подразделения обязательно.

При экстренных обстоятельствах допускается оформление отпуска по согласованию
с HR в срок до 3 рабочих дней.

Компенсация неиспользованного отпуска при увольнении рассчитывается по правилам
трудового законодательства и внутреннему положению банка.
"""


class Command(BaseCommand):
    help = "Create demo assistant_hr KB + document and reindex embeddings"

    def handle(self, *args, **options):
        existing = AssistantKnowledgeBase.objects.filter(slug=DEMO_SLUG).first()
        if existing is None:
            kb = create_assistant_kb(
                {
                    "name": "HR policies",
                    "slug": DEMO_SLUG,
                    "scope": "hr",
                    "description": "Demo KB for local RAG chat",
                },
                username="seed_assistant_rag_demo",
            )
            kb_id = int(kb["id"])
            self.stdout.write(f"Created KB {DEMO_SLUG} id={kb_id}")
        else:
            kb_id = existing.pk
            self.stdout.write(f"Using existing KB {DEMO_SLUG} id={kb_id}")

        upload_assistant_document(
            kb_id,
            filename=DEMO_FILENAME,
            content_type="text/plain",
            data=DEMO_TEXT.encode("utf-8"),
            username="seed_assistant_rag_demo",
            reindex=True,
        )
        result = reindex_assistant_kb(kb_id)
        catalog = list_assistant_kbs(seed=False)
        self.stdout.write(self.style.SUCCESS(
            f"Reindexed: {result}; catalog={catalog}"
        ))
