"""Drop assistant monitoring events older than the one-year journal window."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from assistant.models import AssistantRequestEvent


class Command(BaseCommand):
    help = (
        "Delete assistant monitoring events older than 366 days. "
        "Does not run during a chat request."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=366,
            help="Keep events newer than this many days (default 366).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count rows that would be deleted.",
        )

    def handle(self, *args, **options) -> None:
        days = int(options["days"])
        if days < 1:
            self.stderr.write("days must be >= 1")
            return
        cutoff = timezone.now() - timedelta(days=days)
        queryset = AssistantRequestEvent.objects.filter(created_at__lt=cutoff)
        count = queryset.count()
        if options["dry_run"]:
            self.stdout.write(f"would delete {count}")
            return
        deleted, _ = queryset.delete()
        self.stdout.write(f"deleted {deleted}")
