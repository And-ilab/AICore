"""INT-10: load published SUZ articles into cc_production."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from ingest.bitrix_client import BitrixAuthError
from ingest.full_load import (
    FullLoadConfigError,
    FullLoadPageError,
    FullLoadResult,
    resolve_iblock_id,
    run_full_load,
)


class Command(BaseCommand):
    help = (
        "INT-10 full load: list published Bitrix articles and index them "
        "into cc_production. Does not require Celery."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--iblock-id",
            type=int,
            default=None,
            help="SUZ iblock id. Optional when SUZ_ALLOWED_IBLOCK_IDS has one id.",
        )
        parser.add_argument(
            "--start",
            type=int,
            default=0,
            help="Bitrix list offset to resume from.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Stop after this many articles. 0 means no limit.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List article ids without fetching or indexing them.",
        )

    def handle(self, *args, **options):
        try:
            iblock_id = resolve_iblock_id(options["iblock_id"])
        except FullLoadConfigError as exc:
            raise CommandError(str(exc)) from exc

        try:
            result = run_full_load(
                iblock_id=iblock_id,
                start=options["start"],
                limit=options["limit"],
                dry_run=options["dry_run"],
            )
        except FullLoadConfigError as exc:
            raise CommandError(str(exc)) from exc
        except BitrixAuthError as exc:
            raise CommandError(str(exc)) from exc
        except FullLoadPageError as exc:
            self._write_result(exc.result, dry_run=options["dry_run"])
            raise CommandError(
                f"{exc}. Resume with --start {exc.start}"
            ) from exc

        self._write_result(result, dry_run=options["dry_run"])

    def _write_result(self, result: FullLoadResult, *, dry_run: bool) -> None:
        next_start = "none" if result.next_start is None else str(result.next_start)
        if dry_run:
            self.stdout.write(f"listed: {len(result.listed_ids)}")
            self.stdout.write(
                "ids: " + (", ".join(str(item) for item in result.listed_ids) or "-")
            )
            self.stdout.write(f"next_start: {next_start}")
            return

        self.stdout.write(f"indexed: {result.indexed}")
        self.stdout.write(f"unchanged: {result.unchanged}")
        self.stdout.write(f"skipped: {result.skipped}")
        self.stdout.write(f"deleted: {result.deleted}")
        self.stdout.write(f"errors: {result.errors}")
        self.stdout.write(f"next_start: {next_start}")
        for failure in result.failures[:20]:
            self.stdout.write(
                f"error article_id={failure.article_id}: {failure.error}"
            )
        remaining = len(result.failures) - 20
        if remaining > 0:
            self.stdout.write(f"error ... {remaining} more")
