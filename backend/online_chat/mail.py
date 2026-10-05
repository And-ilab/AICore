"""Build and send dialog transcript e-mails (§4.4.28)."""

from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from online_chat.models import Dialog, DialogMessage, DialogTranscriptEmail

SPEAKER_LABELS = {
    DialogMessage.Speaker.CLIENT: "Клиент",
    DialogMessage.Speaker.OPERATOR: "Оператор",
    DialogMessage.Speaker.SYSTEM: "Система",
}


def build_transcript_body(dialog: Dialog) -> str:
    topic = (dialog.close_topic or "").strip() or "не указана"
    lines = [
        "Беларусбанк — переписка онлайн-консультанта",
        f"Обращение: № {dialog.ref_code()}",
        f"Клиент: {dialog.client_display_name()}",
        f"Телефон: {dialog.client_phone or '—'}",
        f"Оператор: {dialog.operator_name or '—'}",
        f"Тематика закрытия: {topic}",
        f"Закрыт: {dialog.closed_at.isoformat() if dialog.closed_at else '—'}",
        "",
        "— Переписка —",
        "",
    ]
    for message in dialog.messages.all():
        if message.is_deleted:
            continue
        label = SPEAKER_LABELS.get(message.speaker, message.speaker)
        created = message.created_at
        try:
            stamp = timezone.localtime(created).strftime("%d.%m.%Y %H:%M")
        except (TypeError, ValueError, OverflowError):
            stamp = str(created)
        body = message.text
        if message.quoted_text:
            body = f"(в ответ на: {message.quoted_text}) {body}"
        if message.attachment_name:
            body = f"{body} [файл: {message.attachment_name}]"
        lines.append(f"[{stamp}] {label}: {body}")
    lines.extend(
        [
            "",
            "—",
            "Это автоматическое письмо. Пожалуйста, не отвечайте на него.",
        ],
    )
    return "\n".join(lines)


def send_dialog_transcript(
    dialog: Dialog,
    *,
    email: str,
) -> DialogTranscriptEmail:
    dialog.refresh_from_db()
    record = DialogTranscriptEmail.objects.create(
        dialog=dialog,
        email=email.strip(),
        status=DialogTranscriptEmail.Status.PENDING,
    )
    topic = (dialog.close_topic or "").strip()
    base_subject = getattr(
        settings,
        "ONLINE_CHAT_TRANSCRIPT_SUBJECT",
        "Беларусбанк: переписка с онлайн-консультантом",
    )
    subject = f"{base_subject} · {topic}" if topic else base_subject
    from_email = getattr(
        settings,
        "ONLINE_CHAT_FROM_EMAIL",
        None,
    ) or getattr(settings, "DEFAULT_FROM_EMAIL", "online-chat@belarusbank.by")
    body = build_transcript_body(dialog)
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[record.email],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001 — persist delivery failure for ops
        record.status = DialogTranscriptEmail.Status.FAILED
        record.error_detail = str(exc)[:2000]
        record.save(update_fields=["status", "error_detail"])
        return record

    record.status = DialogTranscriptEmail.Status.SENT
    record.sent_at = timezone.now()
    record.save(update_fields=["status", "sent_at"])
    return record
