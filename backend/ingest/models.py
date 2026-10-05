from __future__ import annotations

from django.db import models
from pgvector.django import VectorField


class KnowledgeIngestEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, editable=False)
    article_id = models.BigIntegerField(db_index=True)
    version_id = models.BigIntegerField(null=True, blank=True)
    event_type = models.CharField(max_length=64)
    checksum = models.CharField(max_length=80, blank=True)
    outcome = models.CharField(max_length=32)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)


class SuzReconcileState(models.Model):
    """Singleton cursor for INT-09 Bitrix /changes polling (Model B fallback)."""

    id = models.PositiveSmallIntegerField(
        primary_key=True,
        default=1,
        editable=False,
    )
    cursor = models.CharField(
        max_length=64,
        default="1970-01-01T00:00:00+00:00",
    )
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_accepted = models.PositiveIntegerField(default=0)
    last_skipped = models.PositiveIntegerField(default=0)
    last_failed = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "SUZ reconcile state"
        verbose_name_plural = "SUZ reconcile state"

    def __str__(self) -> str:
        return f"SuzReconcileState(cursor={self.cursor})"


class CCProductionChunk(models.Model):
    """One searchable article fragment in the cc_production pgvector index."""

    article_id = models.BigIntegerField(db_index=True)
    version_id = models.BigIntegerField()
    chunk_index = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    content = models.TextField()
    permalink = models.URLField(max_length=1000)
    locale = models.CharField(max_length=8)
    visibility_scope = models.JSONField(default=list)
    checksum = models.CharField(max_length=80)
    embedding_model = models.CharField(max_length=255)
    embedding = VectorField(dimensions=1024)
    is_active = models.BooleanField(default=True, db_index=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "cc_production"
        ordering = ("article_id", "chunk_index")
        constraints = [
            models.UniqueConstraint(
                fields=("article_id", "version_id", "chunk_index"),
                name="cc_prod_article_version_chunk_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("article_id", "is_active"),
                name="cc_prod_article_active_idx",
            )
        ]


class AssistantProductionChunk(models.Model):
    """Searchable fragment in the assistant_* pgvector index (not cc_production)."""

    kb_slug = models.SlugField(max_length=200, db_index=True)
    article_id = models.BigIntegerField(db_index=True)
    version_id = models.BigIntegerField()
    chunk_index = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    content = models.TextField()
    permalink = models.URLField(max_length=1000)
    locale = models.CharField(max_length=8)
    visibility_scope = models.JSONField(default=list)
    checksum = models.CharField(max_length=80)
    embedding_model = models.CharField(max_length=255)
    embedding = VectorField(dimensions=1024)
    is_active = models.BooleanField(default=True, db_index=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assistant_production"
        ordering = ("kb_slug", "article_id", "chunk_index")
        constraints = [
            models.UniqueConstraint(
                fields=("kb_slug", "article_id", "version_id", "chunk_index"),
                name="asst_prod_chunk_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("kb_slug", "article_id", "is_active"),
                name="asst_prod_active_idx",
            )
        ]
