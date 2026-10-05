"""ASR QA catalogue models (FR-ASR-10 / UC-REP-CC-02)."""

from __future__ import annotations

import uuid

from django.db import models


class AsrDialogueSession(models.Model):
    """Completed telephony/chat dialogue available for analyst QA."""

    CHANNEL_TELEPHONY = "telephony"
    CHANNEL_CHAT = "online_chat"
    CHANNEL_CHOICES = (
        (CHANNEL_TELEPHONY, "Телефония"),
        (CHANNEL_CHAT, "Онлайн-чат"),
    )

    STATUS_RECOGNIZED = "recognized"
    STATUS_UNRECOGNIZED = "unrecognized"
    STATUS_PARTIAL = "partial"
    STATUS_CHOICES = (
        (STATUS_RECOGNIZED, "Распознано"),
        (STATUS_UNRECOGNIZED, "Не распознано"),
        (STATUS_PARTIAL, "Частично"),
    )

    session_id = models.CharField(max_length=64, unique=True, db_index=True)
    channel = models.CharField(max_length=32, choices=CHANNEL_CHOICES)
    operator_id = models.CharField(max_length=64, blank=True)
    operator_name = models.CharField(max_length=255, blank=True)
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField()
    duration_sec = models.PositiveIntegerField(default=0)
    avg_confidence = models.FloatField(default=0.0)
    min_confidence = models.FloatField(default=0.0)
    recognition_status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_PARTIAL,
        db_index=True,
    )
    audio_url = models.CharField(max_length=512, blank=True)
    has_training_candidate = models.BooleanField(default=False, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-started_at",)
        verbose_name = "ASR dialogue session"
        verbose_name_plural = "ASR dialogue sessions"

    def __str__(self) -> str:
        return f"{self.session_id} ({self.channel})"


class AsrTranscriptUtterance(models.Model):
    """One timed transcript line with ASR confidence."""

    SPEAKER_OPERATOR = "operator"
    SPEAKER_CLIENT = "client"
    SPEAKER_CHOICES = (
        (SPEAKER_OPERATOR, "Оператор"),
        (SPEAKER_CLIENT, "Клиент"),
    )

    session = models.ForeignKey(
        AsrDialogueSession,
        on_delete=models.CASCADE,
        related_name="utterances",
    )
    turn_index = models.PositiveIntegerField()
    speaker = models.CharField(max_length=32, choices=SPEAKER_CHOICES)
    text = models.TextField(blank=True)
    confidence = models.FloatField(default=0.0)
    start_ms = models.PositiveIntegerField(default=0)
    end_ms = models.PositiveIntegerField(default=0)
    is_unrecognized = models.BooleanField(default=False)
    training_candidate = models.BooleanField(default=False, db_index=True)
    exemplar_candidate = models.BooleanField(default=False)
    annotated_by = models.CharField(max_length=150, blank=True)
    annotated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("turn_index",)
        unique_together = (("session", "turn_index"),)
        verbose_name = "ASR transcript utterance"
        verbose_name_plural = "ASR transcript utterances"

    def __str__(self) -> str:
        return f"{self.session.session_id}:{self.turn_index}"


class CcReportTemplate(models.Model):
    """Saved CC report builder template."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    metrics = models.JSONField(default=list)
    view_mode = models.CharField(max_length=32, default="table")
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    owner_username = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        verbose_name = "CC report template"
        verbose_name_plural = "CC report templates"

    def __str__(self) -> str:
        return self.name

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "metrics": self.metrics,
            "view_mode": self.view_mode,
            "date_from": self.date_from.isoformat() if self.date_from else None,
            "date_to": self.date_to.isoformat() if self.date_to else None,
            "filters": self.filters or {},
            "owner_username": self.owner_username,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
