"""Seed CC-SCR-001…050 dialog scenarios and QU no-hint / start examples."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from hub.models import DialogScenario
from hub.scenario_catalog import ALL_SCENARIOS, NO_HINT_EXAMPLES
from hub.scenario_service import upsert_from_catalog
from qu.admin_service import hash_question
from qu.models import QuReferenceExample


class Command(BaseCommand):
    help = "Load 10 reference CC scenarios, 40 drafts, and QU no-hint examples"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="seed_cc_scenarios",
            help="updated_by / created_by value",
        )

    def handle(self, *args, **options):
        username = str(options["username"])
        created = 0
        updated = 0
        for payload in ALL_SCENARIOS:
            code = payload["code"]
            existed = DialogScenario.objects.filter(code=code).exists()
            upsert_from_catalog(payload, username=username)
            if existed:
                updated += 1
            else:
                created += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Scenarios upserted: created={created} updated={updated} total={len(ALL_SCENARIOS)}"
            )
        )
        examples = 0
        for intent_id, question in NO_HINT_EXAMPLES:
            examples += _ensure_example(question, intent_id, username)
        for payload in ALL_SCENARIOS:
            if payload.get("status") != "production":
                continue
            nodes = (payload.get("graph") or {}).get("nodes") or []
            start = next((node for node in nodes if node.get("type") == "start"), None)
            if not start:
                continue
            intent = str(start.get("intent_id") or payload["code"])
            for question in start.get("examples") or []:
                examples += _ensure_example(question, intent, username)
        self.stdout.write(self.style.SUCCESS(f"QU examples ensured: {examples} new"))


def _ensure_example(question: str, intent_id: str, username: str) -> int:
    text = (question or "").strip()
    if not text:
        return 0
    digest = hash_question(text)
    existing = QuReferenceExample.objects.filter(question_hash=digest).first()
    if existing:
        return 0
    QuReferenceExample.objects.create(
        question=text[:1000],
        question_hash=digest,
        intent_id=intent_id[:128],
        locale="ru",
        status=QuReferenceExample.STATUS_ACTIVE,
        is_active=True,
        source=QuReferenceExample.SOURCE_MANUAL,
        created_by=username,
        channel="telephony",
    )
    return 1
