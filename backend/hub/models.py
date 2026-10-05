from __future__ import annotations

import math

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class ModelRegistrySettings(models.Model):
    """Database-backed editable parameters for one LLM profile."""

    PROFILE_ASSISTANT = "assistant_bank"
    PROFILE_SUFLER_CC = "sufler_cc"
    PROFILE_CHOICES = (
        (PROFILE_ASSISTANT, "Assistant Bank"),
        (PROFILE_SUFLER_CC, "Sufler Contact Center"),
    )

    PRESET_SHORT = "short"
    PRESET_STANDARD = "standard"
    PRESET_LONG = "long"
    PRESET_CHOICES = (
        (PRESET_SHORT, "Краткий"),
        (PRESET_STANDARD, "Стандарт"),
        (PRESET_LONG, "Развёрнутый"),
    )

    profile = models.CharField(
        max_length=32,
        choices=PROFILE_CHOICES,
        unique=True,
    )
    temperature = models.FloatField()
    top_p = models.FloatField()
    max_tokens = models.PositiveIntegerField()
    response_chars_max = models.PositiveIntegerField()
    preset = models.CharField(
        max_length=16,
        choices=PRESET_CHOICES,
        default=PRESET_STANDARD,
    )
    chunk_size_tokens = models.PositiveIntegerField()
    chunk_overlap_tokens = models.PositiveIntegerField()
    context_inclusion_threshold = models.FloatField()
    deterministic_answer_threshold = models.FloatField()
    revision = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("profile",)
        verbose_name = "Model Registry settings"
        verbose_name_plural = "Model Registry settings"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if (
            not math.isfinite(self.temperature)
            or not 0 <= self.temperature <= 1
        ):
            errors["temperature"] = "Temperature must be between 0 and 1."
        if self.profile == self.PROFILE_SUFLER_CC and not 0.1 <= self.temperature <= 0.25:
            errors["temperature"] = (
                "Sufler CC temperature must be between 0.1 and 0.25."
            )
        if not math.isfinite(self.top_p) or not 0 < self.top_p <= 1:
            errors["top_p"] = "Top P must be greater than 0 and at most 1."
        if not 1 <= self.max_tokens <= 32768:
            errors["max_tokens"] = "Max tokens must be between 1 and 32768."
        response_max = 500 if self.profile == self.PROFILE_SUFLER_CC else 4000
        response_min = 1 if self.profile == self.PROFILE_SUFLER_CC else 10
        if not response_min <= self.response_chars_max <= response_max:
            errors["response_chars_max"] = (
                f"Response length must be between {response_min} and {response_max} characters."
            )
        if self.preset not in {
            self.PRESET_SHORT,
            self.PRESET_STANDARD,
            self.PRESET_LONG,
        }:
            errors["preset"] = "Preset must be short, standard, or long."
        if self.chunk_size_tokens <= 0:
            errors["chunk_size_tokens"] = "Chunk size must be positive."
        if not 0 <= self.chunk_overlap_tokens < self.chunk_size_tokens:
            errors["chunk_overlap_tokens"] = (
                "Chunk overlap must be non-negative and smaller than chunk size."
            )
        for field_name, value in (
            (
                "context_inclusion_threshold",
                self.context_inclusion_threshold,
            ),
            (
                "deterministic_answer_threshold",
                self.deterministic_answer_threshold,
            ),
        ):
            if not math.isfinite(value) or not 0 <= value <= 1:
                errors[field_name] = "Threshold must be between 0 and 1."
        if (
            self.context_inclusion_threshold
            > self.deterministic_answer_threshold
        ):
            errors["deterministic_answer_threshold"] = (
                "Deterministic threshold cannot be lower than context inclusion."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.profile


class ContactCenterKnowledgeBase(models.Model):
    """Admin-managed KB for contact-center sufler (FR-CC-08)."""

    STATUS_IDLE = "idle"
    STATUS_INDEXING = "indexing"
    STATUS_READY = "ready"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_IDLE, "Idle"),
        (STATUS_INDEXING, "Indexing"),
        (STATUS_READY, "Ready"),
        (STATUS_ERROR, "Error"),
    )

    SOURCE_MANUAL = "manual"
    SOURCE_SUZ_BITRIX = "suz_bitrix"
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Ручная загрузка"),
        (SOURCE_SUZ_BITRIX, "СУЗ Битрикс"),
    )

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    scope = models.CharField(max_length=64, default="contact_center")
    description = models.TextField(blank=True)
    source = models.CharField(
        max_length=32,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_IDLE,
        db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    document_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    last_reindexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class KnowledgeBaseDocument(models.Model):
    """Uploaded source document for a contact-center KB (FR-CC-13)."""

    STATUS_UPLOADED = "uploaded"
    STATUS_INDEXED = "indexed"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_INDEXED, "Indexed"),
        (STATUS_ERROR, "Error"),
    )

    knowledge_base = models.ForeignKey(
        ContactCenterKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED,
        db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    extracted_text = models.TextField(blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    article_id = models.BigIntegerField(unique=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return self.filename


class AssistantKnowledgeBase(models.Model):
    """Assistant module KB namespace ``assistant_*`` (isolated from cc_production)."""

    STATUS_IDLE = "idle"
    STATUS_INDEXING = "indexing"
    STATUS_READY = "ready"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_IDLE, "Idle"),
        (STATUS_INDEXING, "Indexing"),
        (STATUS_READY, "Ready"),
        (STATUS_ERROR, "Error"),
    )

    SOURCE_MANUAL = "manual"
    SOURCE_WEBSITE = "website"
    SOURCE_CHOICES = (
        (SOURCE_MANUAL, "Ручная загрузка"),
        (SOURCE_WEBSITE, "Сайт"),
    )

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=200, unique=True)
    scope = models.CharField(max_length=64, default="department")
    description = models.TextField(blank=True)
    source = models.CharField(
        max_length=32,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        db_index=True,
    )
    start_url = models.URLField(max_length=1000, blank=True)
    crawl_depth = models.PositiveSmallIntegerField(default=3)
    max_pages = models.PositiveIntegerField(default=200)
    ignore_robots = models.BooleanField(default=False)
    allowed_hosts = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_IDLE,
        db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    document_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    last_reindexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.slug


class AssistantKnowledgeBaseDocument(models.Model):
    """Uploaded source document for an assistant_* KB (isolated from КЦ)."""

    STATUS_UPLOADED = "uploaded"
    STATUS_INDEXED = "indexed"
    STATUS_ERROR = "error"
    STATUS_CHOICES = (
        (STATUS_UPLOADED, "Uploaded"),
        (STATUS_INDEXED, "Indexed"),
        (STATUS_ERROR, "Error"),
    )

    knowledge_base = models.ForeignKey(
        AssistantKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_UPLOADED,
        db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    extracted_text = models.TextField(blank=True)
    # Relative path under ASSISTANT_KB_STORAGE_ROOT for the original upload.
    original_relpath = models.CharField(max_length=512, blank=True, default="")
    chunk_count = models.PositiveIntegerField(default=0)
    article_id = models.BigIntegerField(unique=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    indexed_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ("-uploaded_at",)

    def __str__(self) -> str:
        return self.filename


class AssistantWebsitePage(models.Model):
    """Crawled page for an assistant_* website KB (idempotent by URL)."""

    knowledge_base = models.ForeignKey(
        AssistantKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="website_pages",
    )
    url = models.URLField(max_length=1000)
    title = models.CharField(max_length=500, blank=True)
    extracted_text = models.TextField(blank=True)
    http_status = models.PositiveSmallIntegerField(default=0)
    content_type = models.CharField(max_length=128, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    article_id = models.BigIntegerField(unique=True)
    checksum = models.CharField(max_length=80, blank=True)
    skipped_reason = models.CharField(max_length=64, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("url",)
        constraints = [
            models.UniqueConstraint(
                fields=("knowledge_base", "url"),
                name="asst_website_page_url_uniq",
            )
        ]

    def __str__(self) -> str:
        return self.url


class AssistantWebsiteCrawlJob(models.Model):
    """Long-running same-domain crawl + index job."""

    STATUS_QUEUED = "queued"
    STATUS_CRAWLING = "crawling"
    STATUS_INDEXING = "indexing"
    STATUS_READY = "ready"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = (
        (STATUS_QUEUED, "Queued"),
        (STATUS_CRAWLING, "Crawling"),
        (STATUS_INDEXING, "Indexing"),
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    )

    knowledge_base = models.ForeignKey(
        AssistantKnowledgeBase,
        on_delete=models.CASCADE,
        related_name="crawl_jobs",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    status_message = models.CharField(max_length=500, blank=True)
    pages_ok = models.PositiveIntegerField(default=0)
    pages_4xx = models.PositiveIntegerField(default=0)
    pages_5xx = models.PositiveIntegerField(default=0)
    pages_skipped = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.knowledge_base_id}:{self.status}"


class AssistantPromptTemplate(models.Model):
    """CRUD prompt templates for assistant_bank (III.10.1 / III.6)."""

    TYPE_SYSTEM = "system"
    TYPE_TASK = "task"
    TYPE_SCOPE = "scope"
    TYPE_CHOICES = (
        (TYPE_SYSTEM, "System"),
        (TYPE_TASK, "Task"),
        (TYPE_SCOPE, "Scope"),
    )
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
    )

    name = models.CharField(max_length=200)
    prompt_type = models.CharField(
        max_length=16,
        choices=TYPE_CHOICES,
        default=TYPE_TASK,
        db_index=True,
    )
    scope = models.CharField(max_length=64, default="bank")
    # Orchestration event for Task skills (capabilities screen), e.g. «Перевод RU→EN».
    event_trigger = models.CharField(max_length=128, blank=True, default="")
    body = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    version = models.PositiveIntegerField(default=1)
    kb_slug = models.SlugField(max_length=200, blank=True, default="")
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("prompt_type", "name")

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class AssistantCapability(models.Model):
    """Tools / skills registry stub for «Навыки» (III.6 / VII.5 D4)."""

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    deep_link = models.CharField(max_length=128, blank=True)
    category = models.CharField(max_length=64, default="tool")
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name")
        verbose_name_plural = "Assistant capabilities"

    def __str__(self) -> str:
        return self.code


class AssistantSkill(models.Model):
    """Slash-command skill library (org «Банк» / user «Мои»). Not a capability."""

    SCOPE_ORG = "org"
    SCOPE_USER = "user"
    SCOPE_CHOICES = (
        (SCOPE_ORG, "Банк"),
        (SCOPE_USER, "Мои"),
    )

    code = models.CharField(max_length=32, blank=True, default="")
    scope = models.CharField(
        max_length=8,
        choices=SCOPE_CHOICES,
        db_index=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="assistant_skills",
    )
    name = models.CharField(max_length=200)
    alias = models.CharField(max_length=64)
    instruction = models.TextField()
    needs_attachment = models.BooleanField(default=False)
    enabled = models.BooleanField(default=True)
    department_scope = models.CharField(max_length=128, blank=True, default="")
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scope", "code", "name")
        constraints = (
            models.UniqueConstraint(
                fields=("alias",),
                condition=Q(scope="org"),
                name="uniq_assistant_skill_org_alias",
            ),
            models.UniqueConstraint(
                fields=("owner", "alias"),
                condition=Q(scope="user"),
                name="uniq_assistant_skill_user_alias",
            ),
            models.UniqueConstraint(
                fields=("code",),
                condition=~Q(code=""),
                name="uniq_assistant_skill_code",
            ),
        )

    def __str__(self) -> str:
        return f"{self.scope}:{self.alias}"


class AssistantDocumentTemplate(models.Model):
    """Bank document blanks for UC-ASS-05 (Word/PDF/Excel/PPT/BPMN)."""

    FORMAT_DOCX = "docx"
    FORMAT_PDF = "pdf"
    FORMAT_XLSX = "xlsx"
    FORMAT_PPTX = "pptx"
    FORMAT_BPMN = "bpmn"
    FORMAT_TXT = "txt"
    FORMAT_MMD = "mmd"
    FORMAT_CHOICES = (
        (FORMAT_DOCX, "Word"),
        (FORMAT_PDF, "PDF"),
        (FORMAT_XLSX, "Excel"),
        (FORMAT_PPTX, "PowerPoint"),
        (FORMAT_BPMN, "BPMN"),
        (FORMAT_TXT, "Текст"),
        (FORMAT_MMD, "Схема / ER"),
    )

    name = models.CharField(max_length=200)
    category = models.CharField(max_length=64, default="Общее")
    output_format = models.CharField(
        max_length=8,
        choices=FORMAT_CHOICES,
        default=FORMAT_DOCX,
        db_index=True,
    )
    body = models.TextField(
        help_text="Текст бланка. Поля подставляются как {{field_id}}.",
    )
    fields = models.JSONField(default=list, blank=True)
    active = models.BooleanField(default=True, db_index=True)
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.output_format})"


class AssistantRpaScenario(models.Model):
    """Whitelist row for an RPA scenario the operator may confirm."""

    name = models.CharField(max_length=200)
    code = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True, db_index=True)
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class AssistantRpaRun(models.Model):
    """Confirmed launch request. The bank robot platform is not called."""

    STATUS_CONFIRMED = "confirmed"
    STATUS_CHOICES = ((STATUS_CONFIRMED, "Подтверждено"),)

    scenario = models.ForeignKey(
        AssistantRpaScenario,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_CONFIRMED,
    )
    detail = models.CharField(max_length=500, blank=True)
    requested_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class AssistantSqlAccess(models.Model):
    """Read-only data mart the assistant may mention in a SQL snippet."""

    name = models.CharField(max_length=200)
    object_name = models.CharField(max_length=80, unique=True)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True, db_index=True)
    updated_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.object_name})"


class TelephonyCallerMemory(models.Model):
    """Last substantive client question, keyed by a real phone number."""

    phone = models.CharField(max_length=32, unique=True)
    question = models.CharField(max_length=240)
    asked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-asked_at",)

    def __str__(self) -> str:
        return self.phone


class SuflerPolicy(models.Model):
    """Operator hint guardrails for sufler_cc (II.3.5.2 / FR-UND-13 / FR-SUF-08/13)."""

    MODE_CONSULTATION = "consultation"
    MODE_SERVICE = "service"
    MODE_CHOICES = (
        (MODE_CONSULTATION, "Консультация"),
        (MODE_SERVICE, "Услуга"),
    )

    telephony_min_relevance_percent = models.PositiveSmallIntegerField(default=20)
    clarify_min_relevance_percent = models.PositiveSmallIntegerField(default=15)
    max_hints = models.PositiveSmallIntegerField(default=1)
    default_mode = models.CharField(
        max_length=16,
        choices=MODE_CHOICES,
        default=MODE_CONSULTATION,
    )
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        verbose_name = "Sufler policy"
        verbose_name_plural = "Sufler policies"

    def clean(self) -> None:
        errors: dict[str, str] = {}
        for field_name in (
            "telephony_min_relevance_percent",
            "clarify_min_relevance_percent",
        ):
            value = int(getattr(self, field_name))
            if not 0 <= value <= 100:
                errors[field_name] = "Порог должен быть от 0 до 100%."
        if not 1 <= int(self.max_hints) <= 5:
            errors["max_hints"] = "На реплику допускается от 1 до 5 подсказок."
        if self.default_mode not in {self.MODE_CONSULTATION, self.MODE_SERVICE}:
            errors["default_mode"] = "Режим должен быть консультация или услуга."
        floor = int(self.telephony_min_relevance_percent)
        if int(self.clarify_min_relevance_percent) > floor:
            errors["clarify_min_relevance_percent"] = (
                "Порог уточнения не может быть выше порога подсказки."
            )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    def min_relevance_for_channel(self, channel: str) -> float:
        """Single operator floor for telephony and online chat."""
        _ = channel
        return int(self.telephony_min_relevance_percent) / 100

    def __str__(self) -> str:
        return f"sufler-policy max={self.max_hints}"


class DialogScenario(models.Model):
    """CC dialog scenario registry (FR-SCR-01…12 / §4.5.2)."""

    STATUS_DRAFT = "draft"
    STATUS_PRODUCTION = "production"
    STATUS_CHOICES = (
        (STATUS_DRAFT, "Черновик"),
        (STATUS_PRODUCTION, "Опубликован"),
    )
    CHANNEL_BOTH = "both"
    CHANNEL_TELEPHONY = "telephony"
    CHANNEL_CHAT = "online_chat"
    CHANNEL_CHOICES = (
        (CHANNEL_BOTH, "Телефония и чат"),
        (CHANNEL_TELEPHONY, "Телефония"),
        (CHANNEL_CHAT, "Онлайн-чат"),
    )

    code = models.CharField(max_length=32, unique=True)
    title = models.CharField(max_length=200)
    root_question = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    channels = models.CharField(
        max_length=32,
        choices=CHANNEL_CHOICES,
        default=CHANNEL_BOTH,
    )
    current_version = models.ForeignKey(
        "DialogScenarioVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code


class DialogScenarioVersion(models.Model):
    """Published or draft graph/prompt snapshot (FR-SCR-03)."""

    scenario = models.ForeignKey(
        DialogScenario,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_number = models.PositiveIntegerField(default=1)
    graph = models.JSONField(default=dict)
    system_prompt = models.TextField(blank=True, default="")
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        ordering = ("-version_number",)
        unique_together = ("scenario", "version_number")

    def __str__(self) -> str:
        return f"{self.scenario_id} v{self.version_number}"


class DialogScenarioSession(models.Model):
    """Live walk through a scenario for one call/chat."""

    session_key = models.CharField(max_length=160, unique=True)
    scenario = models.ForeignKey(
        DialogScenario,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    node_id = models.CharField(max_length=64)
    path = models.JSONField(default=list)
    paused = models.BooleanField(default=False)
    off_topic_count = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)

    def __str__(self) -> str:
        return f"{self.session_key} → {self.node_id}"
