"""Persisted assistant monitoring events and report definitions."""

from __future__ import annotations

from django.db import models


class AssistantRequestEvent(models.Model):
    """One completed assistant chat turn, written after the reply is sent.

    Dialog text is stored so the error and hallucination reports required by
    §5.4 can be opened later. It is not written to logs.
    """

    QUERY_RAG = "rag_kb"
    QUERY_SUMMARY = "attachment_summary"
    QUERY_SKILL = "skill"
    QUERY_NO_KB = "no_kb"
    QUERY_FILTER = "content_filter"
    QUERY_LLM_ERROR = "llm_error"
    QUERY_TYPE_CHOICES = (
        (QUERY_RAG, "Поиск по базе"),
        (QUERY_SUMMARY, "Резюме вложения"),
        (QUERY_SKILL, "Навык"),
        (QUERY_NO_KB, "Нет данных в базе"),
        (QUERY_FILTER, "Фильтр контента"),
        (QUERY_LLM_ERROR, "Ошибка модели"),
    )

    OUTCOME_STREAMED = "streamed"
    OUTCOME_NO_KB = "no_kb"
    OUTCOME_FILTER = "content_filter"
    OUTCOME_LLM_ERROR = "llm_error"
    OUTCOME_CLIENT_CLOSED = "client_closed"
    OUTCOME_ERROR = "error"
    OUTCOME_CHOICES = (
        (OUTCOME_STREAMED, "Ответ отдан"),
        (OUTCOME_NO_KB, "Нет фрагментов"),
        (OUTCOME_FILTER, "Отказ фильтра"),
        (OUTCOME_LLM_ERROR, "Ошибка модели"),
        (OUTCOME_CLIENT_CLOSED, "Клиент прервал"),
        (OUTCOME_ERROR, "Сбой"),
    )

    REASON_NONE = ""
    REASON_NO_SOURCES = "no_sources"
    REASON_LOW_RELEVANCE = "low_relevance"
    REASON_LLM_ERROR = "llm_error"
    REASON_CONTENT_FILTER = "content_filter"
    REASON_CHOICES = (
        (REASON_NONE, ""),
        (REASON_NO_SOURCES, "Нет данных в базе"),
        (REASON_LOW_RELEVANCE, "Релевантность ниже порога"),
        (REASON_LLM_ERROR, "Ошибка модели"),
        (REASON_CONTENT_FILTER, "Отказ фильтра"),
    )

    request_id = models.CharField(max_length=64, unique=True)
    message_id = models.CharField(max_length=64, blank=True, default="")
    session_id = models.CharField(max_length=64, blank=True, default="")
    username = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    query_type = models.CharField(max_length=32, choices=QUERY_TYPE_CHOICES)
    topic = models.CharField(max_length=255, default="без источника")
    outcome = models.CharField(max_length=32, choices=OUTCOME_CHOICES)
    error_reason = models.CharField(
        max_length=32,
        blank=True,
        default="",
        choices=REASON_CHOICES,
    )
    total_ms = models.FloatField(null=True, blank=True)
    ttft_ms = models.FloatField(null=True, blank=True)
    llm_ms = models.FloatField(null=True, blank=True)
    top_relevance = models.FloatField(null=True, blank=True)
    doc_count = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(null=True, blank=True)
    kb_slugs = models.JSONField(default=list, blank=True)
    source_title = models.CharField(max_length=255, blank=True, default="")
    question_text = models.TextField(blank=True, default="")
    answer_text = models.TextField(blank=True, default="")
    hallucination_marked = models.BooleanField(default=False)
    hallucination_marked_by_id = models.PositiveIntegerField(null=True, blank=True)
    hallucination_marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(
                fields=["created_at", "department"],
                name="ass_mon_evt_created_dept_idx",
            ),
            models.Index(
                fields=["created_at", "query_type"],
                name="ass_mon_evt_created_type_idx",
            ),
            models.Index(
                fields=["created_at", "outcome"],
                name="ass_mon_evt_created_out_idx",
            ),
            models.Index(fields=["message_id"], name="ass_mon_evt_message_idx"),
        ]
        verbose_name = "Assistant request event"
        verbose_name_plural = "Assistant request events"

    def __str__(self) -> str:
        return self.request_id


class AssistantReportTemplate(models.Model):
    """Saved metric set for the report builder (§5.4.5)."""

    FORMAT_CSV = "csv"
    FORMAT_XLSX = "xlsx"
    FORMAT_CHOICES = (
        (FORMAT_CSV, "CSV"),
        (FORMAT_XLSX, "XLSX"),
    )

    name = models.CharField(max_length=200)
    metrics = models.JSONField(default=list)
    export_format = models.CharField(
        max_length=8,
        choices=FORMAT_CHOICES,
        default=FORMAT_CSV,
    )
    created_by_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")
        verbose_name = "Assistant report template"
        verbose_name_plural = "Assistant report templates"

    def __str__(self) -> str:
        return self.name


class AssistantReportSchedule(models.Model):
    """Regular report cadence (§5.4.3). Generation itself is a Celery task."""

    CADENCE_DAILY = "daily"
    CADENCE_WEEKLY = "weekly"
    CADENCE_MONTHLY = "monthly"
    CADENCE_CHOICES = (
        (CADENCE_DAILY, "Ежедневно"),
        (CADENCE_WEEKLY, "Еженедельно"),
        (CADENCE_MONTHLY, "Ежемесячно"),
    )
    STATUS_NEVER = "never"
    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_NEVER, "Не запускалось"),
        (STATUS_OK, "Готово"),
        (STATUS_ERROR, "Ошибка"),
    )

    cadence = models.CharField(max_length=16, choices=CADENCE_CHOICES)
    report_id = models.CharField(max_length=32, blank=True, default="")
    template = models.ForeignKey(
        AssistantReportTemplate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="schedules",
    )
    enabled = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_NEVER,
    )
    last_error = models.CharField(max_length=64, blank=True, default="")
    last_summary = models.JSONField(default=dict, blank=True)
    created_by_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("cadence", "id")
        verbose_name = "Assistant report schedule"
        verbose_name_plural = "Assistant report schedules"

    def __str__(self) -> str:
        return f"{self.cadence}:{self.report_id or self.pk}"
