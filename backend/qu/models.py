from __future__ import annotations

from django.db import models


class QuReferenceExample(models.Model):
    """Эталон обучающей выборки QU (II.2.6 / FR-UND-04)."""

    STATUS_ACTIVE = "active"
    STATUS_PENDING = "pending_review"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = (
        (STATUS_ACTIVE, "Активен"),
        (STATUS_PENDING, "На модерации"),
        (STATUS_REJECTED, "Отклонён"),
    )

    SOURCE_MANUAL = "manual"
    SOURCE_DIALOG = "dialog"
    SOURCE_ASR = "asr_qa"
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Ручное добавление"),
        (SOURCE_DIALOG, "Диалог"),
        (SOURCE_ASR, "QA ASR"),
    )

    question = models.CharField(max_length=1000)
    question_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    article_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    article_title = models.CharField(max_length=255, blank=True, default="")
    intent_id = models.CharField(max_length=128, blank=True)
    synonyms = models.TextField(blank=True, default="")
    locale = models.CharField(max_length=8, default="ru")
    status = models.CharField(
        max_length=24,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        db_index=True,
    )
    is_active = models.BooleanField(default=True, db_index=True)
    source = models.CharField(
        max_length=32,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        db_index=True,
    )
    source_feedback_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    original_hint = models.TextField(blank=True, default="")
    relevance_percent = models.PositiveSmallIntegerField(null=True, blank=True)
    operator_name = models.CharField(max_length=160, blank=True, default="")
    channel = models.CharField(max_length=32, blank=True, default="")
    admin_comment = models.TextField(blank=True, default="")
    created_by = models.CharField(max_length=150, blank=True, default="")
    reviewed_by = models.CharField(max_length=150, blank=True, default="")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-id")

    def __str__(self) -> str:
        return self.question


class QuReplenishmentPolicy(models.Model):
    """Политика пополнения эталонов QU (FR-UND-09)."""

    MODE_SUGGEST = "suggest"
    MODE_AUTO_CONFIRM = "auto_with_confirmation"
    MODE_AUTO = "auto"
    MODE_CHOICES = (
        (MODE_SUGGEST, "Предлагать (без автозаписи)"),
        (MODE_AUTO_CONFIRM, "Черновик на модерацию"),
        (MODE_AUTO, "Автодобавление"),
    )

    mode = models.CharField(
        max_length=32,
        choices=MODE_CHOICES,
        default=MODE_AUTO_CONFIRM,
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        verbose_name = "QU replenishment policy"
        verbose_name_plural = "QU replenishment policies"

    def __str__(self) -> str:
        return self.mode
