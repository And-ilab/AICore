"""Verify PostgreSQL + pgvector data tier from the Django backend."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = (
        "Verify backend DB connection, pgvector extension, and "
        "cc_production HNSW index (TEST/PROD data tier)."
    )

    def handle(self, *args, **options):
        vendor = connection.vendor
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone()[0] != 1:
                raise CommandError("SELECT 1 failed")

        self.stdout.write(self.style.SUCCESS(f"connection: ok ({vendor})"))

        if vendor != "postgresql":
            self.stdout.write(
                self.style.WARNING(
                    "skip pgvector checks (not PostgreSQL — local sqlite OK)"
                )
            )
            return

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT extversion FROM pg_extension WHERE extname = %s",
                ["vector"],
            )
            row = cursor.fetchone()
            if not row:
                raise CommandError(
                    "pgvector extension 'vector' missing — "
                    "run infra/test/sql/ensure_pgvector.sql"
                )
            self.stdout.write(
                self.style.SUCCESS(f"pgvector: ok (version {row[0]})")
            )

            cursor.execute(
                """
                SELECT 1
                FROM pg_indexes
                WHERE tablename = 'cc_production'
                  AND indexname = 'cc_prod_embedding_hnsw_idx'
                """
            )
            if cursor.fetchone() is None:
                raise CommandError(
                    "index cc_prod_embedding_hnsw_idx missing on cc_production — "
                    "run migrate + infra/test/sql/ensure_pgvector.sql"
                )
            self.stdout.write(
                self.style.SUCCESS("index: cc_prod_embedding_hnsw_idx ok")
            )

            cursor.execute("SELECT COUNT(*) FROM cc_production")
            count = cursor.fetchone()[0]
            self.stdout.write(f"cc_production rows: {count}")

        self.stdout.write(self.style.SUCCESS("verify_data_tier: OK"))
