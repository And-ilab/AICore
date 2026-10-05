"""ASR QA catalogue service (FR-ASR-10 / UC-REP-CC-02)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping
import io
import logging
import struct
import wave

from django.db import transaction
from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from reports.models import AsrDialogueSession, AsrTranscriptUtterance

logger = logging.getLogger(__name__)

# Прил.1 §4.7.3.5: success < 90% → low confidence highlight / optional filter.
ASR_LOW_CONFIDENCE_THRESHOLD = 0.90
TTL_DAYS = 365


class AsrQaError(ValueError):
    """Validation error for ASR QA API."""


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return value.isoformat()


def _parse_dt(raw: str | None, *, field: str) -> datetime | None:
    if raw is None or raw == "":
        return None
    parsed = parse_datetime(raw)
    if parsed is None:
        raise AsrQaError(f"{field} must be an ISO datetime")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def serialize_utterance(utterance: AsrTranscriptUtterance) -> dict[str, Any]:
    low = utterance.confidence < ASR_LOW_CONFIDENCE_THRESHOLD
    return {
        "id": utterance.pk,
        "turn_index": utterance.turn_index,
        "speaker": utterance.speaker,
        "text": utterance.text,
        "confidence": round(utterance.confidence, 4),
        "start_ms": utterance.start_ms,
        "end_ms": utterance.end_ms,
        "is_unrecognized": utterance.is_unrecognized,
        "low_confidence": low or utterance.is_unrecognized,
        "training_candidate": utterance.training_candidate,
        "exemplar_candidate": utterance.exemplar_candidate,
        "annotated_by": utterance.annotated_by,
        "annotated_at": _iso(utterance.annotated_at),
    }


def serialize_session(
    session: AsrDialogueSession,
    *,
    include_utterances: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": session.pk,
        "session_id": session.session_id,
        "channel": session.channel,
        "operator_id": session.operator_id,
        "operator_name": session.operator_name,
        "started_at": _iso(session.started_at),
        "ended_at": _iso(session.ended_at),
        "duration_sec": session.duration_sec,
        "avg_confidence": round(session.avg_confidence, 4),
        "min_confidence": round(session.min_confidence, 4),
        "recognition_status": session.recognition_status,
        "audio_url": session.audio_url,
        "has_training_candidate": session.has_training_candidate,
        "expires_at": _iso(session.expires_at),
        "low_confidence_threshold": ASR_LOW_CONFIDENCE_THRESHOLD,
    }
    if include_utterances:
        payload["utterances"] = [
            serialize_utterance(item) for item in session.utterances.all()
        ]
    return payload


def _base_queryset() -> QuerySet[AsrDialogueSession]:
    now = timezone.now()
    return AsrDialogueSession.objects.filter(expires_at__gte=now)


def list_sessions(
    *,
    channel: str | None = None,
    operator: str | None = None,
    recognition_status: str | None = None,
    low_confidence_only: bool = False,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict[str, Any]]:
    qs = _base_queryset()
    if channel:
        if channel not in {
            AsrDialogueSession.CHANNEL_TELEPHONY,
            AsrDialogueSession.CHANNEL_CHAT,
        }:
            raise AsrQaError("channel must be telephony or online_chat")
        qs = qs.filter(channel=channel)
    if operator:
        qs = qs.filter(
            Q(operator_name__icontains=operator)
            | Q(operator_id__icontains=operator)
        )
    if recognition_status:
        allowed = {
            AsrDialogueSession.STATUS_RECOGNIZED,
            AsrDialogueSession.STATUS_UNRECOGNIZED,
            AsrDialogueSession.STATUS_PARTIAL,
        }
        if recognition_status not in allowed:
            raise AsrQaError("invalid recognition_status")
        qs = qs.filter(recognition_status=recognition_status)
    started_from = _parse_dt(date_from, field="date_from")
    started_to = _parse_dt(date_to, field="date_to")
    if started_from is not None:
        qs = qs.filter(started_at__gte=started_from)
    if started_to is not None:
        qs = qs.filter(started_at__lte=started_to)
    if low_confidence_only:
        qs = qs.filter(min_confidence__lt=ASR_LOW_CONFIDENCE_THRESHOLD)

    return [serialize_session(item) for item in qs]


def get_session(session_pk: int) -> dict[str, Any]:
    session = (
        _base_queryset()
        .prefetch_related(
            Prefetch(
                "utterances",
                queryset=AsrTranscriptUtterance.objects.order_by("turn_index"),
            )
        )
        .get(pk=session_pk)
    )
    return serialize_session(session, include_utterances=True)


def set_training_candidate(
    session_pk: int,
    utterance_id: int,
    *,
    training_candidate: bool,
    username: str,
) -> dict[str, Any]:
    try:
        utterance = AsrTranscriptUtterance.objects.select_related("session").get(
            pk=utterance_id,
            session_id=session_pk,
        )
    except AsrTranscriptUtterance.DoesNotExist as exc:
        raise AsrDialogueSession.DoesNotExist from exc

    utterance.training_candidate = bool(training_candidate)
    utterance.annotated_by = username
    utterance.annotated_at = timezone.now()
    utterance.save(
        update_fields=[
            "training_candidate",
            "annotated_by",
            "annotated_at",
        ]
    )
    session = utterance.session
    session.has_training_candidate = session.utterances.filter(
        training_candidate=True
    ).exists()
    session.save(update_fields=["has_training_candidate", "updated_at"])
    if utterance.training_candidate:
        try:
            from qu.admin_service import enqueue_from_asr_utterance

            enqueue_from_asr_utterance(utterance, session=session)
        except Exception:
            logger.exception("QU enqueue from ASR candidate failed")
    return {
        "utterance": serialize_utterance(utterance),
        "session": serialize_session(session),
    }


def catalogue_stats() -> dict[str, int]:
    qs = _base_queryset()
    return {
        "total": qs.count(),
        "recognized": qs.filter(
            recognition_status=AsrDialogueSession.STATUS_RECOGNIZED
        ).count(),
        "unrecognized": qs.filter(
            recognition_status=AsrDialogueSession.STATUS_UNRECOGNIZED
        ).count(),
        "partial": qs.filter(
            recognition_status=AsrDialogueSession.STATUS_PARTIAL
        ).count(),
        "training_candidates": qs.filter(has_training_candidate=True).count(),
        "low_confidence": qs.filter(
            min_confidence__lt=ASR_LOW_CONFIDENCE_THRESHOLD
        ).count(),
    }


def build_silence_wav(*, duration_sec: float = 1.0, sample_rate: int = 8000) -> bytes:
    """Minimal mono PCM WAV used when a telephony session has no external audio."""
    frames = max(1, int(duration_sec * sample_rate))
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack("<" + "h" * frames, *([0] * frames)))
    return buffer.getvalue()


@transaction.atomic
def seed_demo_sessions(*, force: bool = False) -> list[dict[str, Any]]:
    """Deterministic demo catalogue for FR-ASR-10 acceptance demos/tests."""
    if not force and AsrDialogueSession.objects.exists():
        return list_sessions()

    AsrDialogueSession.objects.all().delete()
    now = timezone.now()
    expires = now + timedelta(days=TTL_DAYS)

    recognized = AsrDialogueSession.objects.create(
        session_id="CALL-QA-001",
        channel=AsrDialogueSession.CHANNEL_TELEPHONY,
        operator_id="op-ivanov",
        operator_name="Иванов И.И.",
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(hours=2) + timedelta(seconds=48),
        duration_sec=48,
        avg_confidence=0.96,
        min_confidence=0.93,
        recognition_status=AsrDialogueSession.STATUS_RECOGNIZED,
        audio_url="/api/reports/asr/sessions/1/audio/",
        expires_at=expires,
    )
    AsrTranscriptUtterance.objects.bulk_create(
        [
            AsrTranscriptUtterance(
                session=recognized,
                turn_index=0,
                speaker=AsrTranscriptUtterance.SPEAKER_OPERATOR,
                text="Здравствуйте, банк на связи, чем могу помочь?",
                confidence=0.98,
                start_ms=0,
                end_ms=4200,
            ),
            AsrTranscriptUtterance(
                session=recognized,
                turn_index=1,
                speaker=AsrTranscriptUtterance.SPEAKER_CLIENT,
                text="Хочу уточнить баланс по карте.",
                confidence=0.93,
                start_ms=4500,
                end_ms=8200,
            ),
            AsrTranscriptUtterance(
                session=recognized,
                turn_index=2,
                speaker=AsrTranscriptUtterance.SPEAKER_OPERATOR,
                text="Сейчас проверю информацию по вашей карте.",
                confidence=0.97,
                start_ms=8500,
                end_ms=12800,
            ),
        ]
    )

    partial = AsrDialogueSession.objects.create(
        session_id="CALL-QA-002",
        channel=AsrDialogueSession.CHANNEL_TELEPHONY,
        operator_id="op-petrova",
        operator_name="Петрова А.С.",
        started_at=now - timedelta(hours=1),
        ended_at=now - timedelta(hours=1) + timedelta(seconds=36),
        duration_sec=36,
        avg_confidence=0.71,
        min_confidence=0.18,
        recognition_status=AsrDialogueSession.STATUS_PARTIAL,
        audio_url="/api/reports/asr/sessions/2/audio/",
        expires_at=expires,
    )
    AsrTranscriptUtterance.objects.bulk_create(
        [
            AsrTranscriptUtterance(
                session=partial,
                turn_index=0,
                speaker=AsrTranscriptUtterance.SPEAKER_CLIENT,
                text="Мне нужно перевыпустить карту из-за утраты.",
                confidence=0.91,
                start_ms=0,
                end_ms=5100,
            ),
            AsrTranscriptUtterance(
                session=partial,
                turn_index=1,
                speaker=AsrTranscriptUtterance.SPEAKER_OPERATOR,
                text="…неразборчиво…",
                confidence=0.18,
                start_ms=5400,
                end_ms=9100,
                is_unrecognized=True,
            ),
            AsrTranscriptUtterance(
                session=partial,
                turn_index=2,
                speaker=AsrTranscriptUtterance.SPEAKER_CLIENT,
                text="Повторю: карта утеряна, нужен перевыпуск.",
                confidence=0.88,
                start_ms=9400,
                end_ms=14100,
            ),
            AsrTranscriptUtterance(
                session=partial,
                turn_index=3,
                speaker=AsrTranscriptUtterance.SPEAKER_OPERATOR,
                text="Оформлю заявление на перевыпуск.",
                confidence=0.86,
                start_ms=14500,
                end_ms=18200,
            ),
        ]
    )

    unrecognized = AsrDialogueSession.objects.create(
        session_id="CHAT-QA-003",
        channel=AsrDialogueSession.CHANNEL_CHAT,
        operator_id="op-sidorov",
        operator_name="Сидоров П.В.",
        started_at=now - timedelta(minutes=40),
        ended_at=now - timedelta(minutes=35),
        duration_sec=300,
        avg_confidence=0.0,
        min_confidence=0.0,
        recognition_status=AsrDialogueSession.STATUS_UNRECOGNIZED,
        audio_url="",
        expires_at=expires,
    )
    AsrTranscriptUtterance.objects.create(
        session=unrecognized,
        turn_index=0,
        speaker=AsrTranscriptUtterance.SPEAKER_CLIENT,
        text="",
        confidence=0.0,
        start_ms=0,
        end_ms=0,
        is_unrecognized=True,
    )

    # Fix audio URLs to real PKs after insert.
    for session in AsrDialogueSession.objects.filter(
        channel=AsrDialogueSession.CHANNEL_TELEPHONY
    ):
        session.audio_url = f"/api/reports/asr/sessions/{session.pk}/audio/"
        session.save(update_fields=["audio_url"])

    return list_sessions()


def parse_filters(params: Mapping[str, Any]) -> dict[str, Any]:
    raw_low = params.get("low_confidence_only", "false")
    if isinstance(raw_low, bool):
        low_only = raw_low
    else:
        low_only = str(raw_low).lower() in {"1", "true", "yes"}
    return {
        "channel": params.get("channel") or None,
        "operator": params.get("operator") or None,
        "recognition_status": params.get("recognition_status") or None,
        "low_confidence_only": low_only,
        "date_from": params.get("date_from") or None,
        "date_to": params.get("date_to") or None,
    }
