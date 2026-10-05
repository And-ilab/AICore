"""OCR job tracking and admin-managed document templates (IV.5 / FR-OCR-20)."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class OcrJob(models.Model):
    STATUS_QUEUED = "queued"
    STATUS_OCR_PROCESSING = "ocr_processing"
    STATUS_COMPLETED = "completed"
    STATUS_ERROR = "processing_error"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_OCR_PROCESSING, "OCR processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ERROR, "Processing error"),
    )

    job_id = models.CharField(max_length=64, primary_key=True)
    document_id = models.CharField(max_length=64, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    sha256 = models.CharField(max_length=64)
    original_object_key = models.CharField(max_length=512)
    result_object_key = models.CharField(max_length=512, blank=True)
    ocr_model = models.CharField(max_length=255, blank=True)
    document_type = models.CharField(max_length=64, blank=True, db_index=True)
    validation_status = models.CharField(max_length=32, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    batch_id = models.CharField(max_length=64, blank=True, db_index=True)
    source_archive = models.CharField(max_length=255, blank=True)
    user_template = models.ForeignKey(
        "OcrUserTemplate",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.job_id} ({self.status})"


class OcrDocumentTemplate(models.Model):
    """Admin-published field schema for a document type (Template Registry)."""

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    )

    doc_type = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    template_version = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    required_fields = models.JSONField(default=list)
    field_schema = models.JSONField(default=dict)
    confidence_min = models.FloatField(default=0.6)
    sample_prompt = models.TextField(
        blank=True,
        help_text="Example OCR text used while training / validating the template",
    )
    owner = models.CharField(max_length=150, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("doc_type",)

    def __str__(self) -> str:
        return f"{self.doc_type} v{self.template_version} ({self.status})"


class OcrTemplateSample(models.Model):
    """Labeled training sample attached to a template by OCR admin."""

    template = models.ForeignKey(
        OcrDocumentTemplate,
        related_name="samples",
        on_delete=models.CASCADE,
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    object_key = models.CharField(max_length=512, blank=True)
    ocr_text = models.TextField(blank=True)
    expected_fields = models.JSONField(default=dict)
    notes = models.TextField(blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"sample:{self.filename}@{self.template.doc_type}"


class OcrUserTemplate(models.Model):
    """Personal OCR field set. Isolated from the bank OcrDocumentTemplate catalog."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ocr_user_templates",
    )
    name = models.CharField(max_length=80)
    name_key = models.CharField(max_length=80)
    fields = models.JSONField(default=list)
    source_job_id = models.CharField(max_length=64, blank=True)
    source_file = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        constraints = (
            models.UniqueConstraint(
                fields=("owner", "name_key"),
                name="uniq_ocr_user_template_owner_name",
            ),
        )

    def __str__(self) -> str:
        return f"user-tpl:{self.owner_id}:{self.name}"
