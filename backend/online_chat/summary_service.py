"""Dialog essence summaries for ARM client history (short + detailed).

Uses ModelGateway when available; falls back to a lightweight extractive
heuristic so local stub mode still returns readable text.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db.models import Prefetch

from online_chat.models import Dialog, DialogMessage

logger = logging.getLogger(__name__)

_PROFILE = "sufler_cc"
_MAX_TRANSCRIPT_CHARS = 4500
_MAX_MESSAGES = 40

_SYSTEM_PROMPT = (
    "Ты помощник оператора контакт-центра. "
    "По переписке клиента и оператора сформулируй суть обращения. "
    "Пиши по-русски, деловым нейтральным стилем. "
    "Не выдумывай факты, которых нет в переписке. "
    "Не указывай дату, тему закрытия, канал, ФИО оператора и номера телефонов. "
    "Не цитируй реплики дословно и не воспроизводи стенограмму.\n"
    "Формат ответа СТРОГО:\n"
    "КРАТКО:\n"
    "<ровно 1–2 средних предложения о сути диалога>\n"
    "ПОДРОБНО:\n"
    "<3–5 предложений: тот же смысл, но чуть развёрнутее — "
    "что хотел клиент, что сделал/объяснил оператор, чем закончилось>"
)


def _speaker_label(speaker: str) -> str:
    if speaker == DialogMessage.Speaker.CLIENT:
        return "Клиент"
    if speaker == DialogMessage.Speaker.BOT:
        return "Бот"
    if speaker == DialogMessage.Speaker.OPERATOR:
        return "Оператор"
    return "Система"


def build_transcript(dialog: Dialog, *, max_messages: int = _MAX_MESSAGES) -> str:
    lines: list[str] = []
    messages = [
        msg
        for msg in dialog.messages.all()
        if not msg.is_deleted
        and msg.speaker
        in {
            DialogMessage.Speaker.CLIENT,
            DialogMessage.Speaker.OPERATOR,
            DialogMessage.Speaker.BOT,
        }
    ][:max_messages]
    for msg in messages:
        text = re.sub(r"\s+", " ", (msg.text or "").strip())
        if not text:
            continue
        if len(text) > 280:
            text = text[:277] + "…"
        lines.append(f"{_speaker_label(msg.speaker)}: {text}")
    transcript = "\n".join(lines)
    if len(transcript) > _MAX_TRANSCRIPT_CHARS:
        transcript = transcript[: _MAX_TRANSCRIPT_CHARS - 1] + "…"
    return transcript


def _clean_sentence_blob(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    cleaned = cleaned.replace("**", "").replace("__", "")
    return cleaned.strip(" \n\t-•")


def _ensure_sentence(text: str) -> str:
    text = _clean_sentence_blob(text)
    if not text:
        return ""
    if text[-1] not in ".!?…":
        text += "."
    return text


def _heuristic_summaries(dialog: Dialog, transcript: str) -> tuple[str, str]:
    client_msgs = [
        re.sub(r"\s+", " ", (msg.text or "").strip())
        for msg in dialog.messages.all()
        if not msg.is_deleted
        and msg.speaker == DialogMessage.Speaker.CLIENT
        and (msg.text or "").strip()
    ]
    operator_msgs = [
        re.sub(r"\s+", " ", (msg.text or "").strip())
        for msg in dialog.messages.all()
        if not msg.is_deleted
        and msg.speaker == DialogMessage.Speaker.OPERATOR
        and (msg.text or "").strip()
    ]
    client_ask = next((m for m in client_msgs if len(m) >= 12), client_msgs[0] if client_msgs else "")
    operator_reply = next(
        (m for m in reversed(operator_msgs) if len(m) >= 20),
        operator_msgs[-1] if operator_msgs else "",
    )
    if client_ask and len(client_ask) > 160:
        client_ask = client_ask[:157] + "…"
    if operator_reply and len(operator_reply) > 180:
        operator_reply = operator_reply[:177] + "…"

    if client_ask and operator_reply:
        ask = client_ask.rstrip(".!?…")
        reply = operator_reply.rstrip(".!?…")
        short = _ensure_sentence(
            f"Клиент обратился по вопросу «{ask}»; "
            f"оператор разъяснил условия и дал практические рекомендации"
        )
        detailed = (
            f"{_ensure_sentence(f'Клиент сформулировал запрос: {ask}')} "
            f"{_ensure_sentence(f'Оператор ответил по сути: {reply}')} "
            "Обращение закрыто после разъяснения."
        )
        return short, detailed

    if client_ask:
        ask = client_ask.rstrip(".!?…")
        short = _ensure_sentence(f"Клиент обратился с вопросом «{ask}»")
        detailed = (
            f"{short} Подробный ответ оператора в переписке отсутствует либо не был сохранён."
        )
        return short, detailed

    preview = (dialog.preview or "").strip()
    if preview:
        short = _ensure_sentence(f"Клиент обращался по вопросу: {preview[:140]}")
        return short, short
    if transcript.strip():
        short = "Клиент обращался в поддержку; по переписке зафиксирован рабочий диалог с оператором."
        return short, short
    return (
        "По обращению недостаточно данных для краткого summary.",
        "По обращению недостаточно данных для детального summary.",
    )


def _parse_llm_summaries(raw: str) -> tuple[str, str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    short_match = re.search(
        r"кратко\s*:\s*(.*?)(?:\n\s*подробно\s*:|$)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    long_match = re.search(
        r"подробно\s*:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    short = _clean_sentence_blob(short_match.group(1) if short_match else "")
    detailed = _clean_sentence_blob(long_match.group(1) if long_match else "")
    if not short and not detailed:
        # Model ignored the template — treat whole answer as short.
        short = _clean_sentence_blob(text)
    if not short:
        return None
    if not detailed:
        detailed = short
    # Keep short to ~2 sentences.
    parts = re.split(r"(?<=[.!?…])\s+", short)
    short = " ".join(parts[:2]).strip()
    return _ensure_sentence(short) if short[-1:] not in ".!?…" else short, detailed


def _llm_summaries(transcript: str) -> tuple[str, str] | None:
    if not transcript.strip():
        return None
    try:
        from core.model_gateway import ModelGateway
        from hub.model_registry_store import get_model_settings
    except Exception:  # noqa: BLE001
        return None

    try:
        settings = get_model_settings(_PROFILE)
        gateway = ModelGateway.from_registry()
        # Stub gateway returns a fixed sufler hint — useless for summaries.
        profile = gateway.get_profile(_PROFILE)
        mode = gateway._mode_for(profile)  # noqa: SLF001
        if mode == "stub" or str(profile.model).startswith("stub:"):
            return None
        response = gateway.chat(
            _PROFILE,
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        "Переписка обращения:\n"
                        f"{transcript}\n\n"
                        "Сформируй КРАТКО и ПОДРОБНО по шаблону."
                    ),
                },
            ],
            temperature=min(float(settings.temperature or 0.2), 0.3),
            max_tokens=min(int(settings.max_tokens or 400), 450),
        )
        content = response["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            return None
        return _parse_llm_summaries(content)
    except Exception as exc:  # noqa: BLE001
        logger.info("dialog_summary_llm_fallback error=%s", exc)
        return None


def summarize_dialog(dialog: Dialog) -> tuple[str, str]:
    transcript = build_transcript(dialog)
    llm = _llm_summaries(transcript)
    if llm:
        return llm
    return _heuristic_summaries(dialog, transcript)


def ensure_dialog_summaries(dialog: Dialog, *, force: bool = False) -> Dialog:
    """Generate and persist short/detailed essence if missing."""
    if (
        not force
        and (dialog.summary_short or "").strip()
        and (dialog.summary_detailed or "").strip()
    ):
        return dialog
    short, detailed = summarize_dialog(dialog)
    dialog.summary_short = short[:2000]
    dialog.summary_detailed = detailed[:4000]
    dialog.save(update_fields=["summary_short", "summary_detailed", "updated_at"])
    return dialog


def combine_short_summaries(parts: list[str], *, limit: int = 3) -> str:
    cleaned = [_clean_sentence_blob(part) for part in parts if _clean_sentence_blob(part)]
    cleaned = cleaned[:limit]
    if not cleaned:
        # Caller already knows there were previous dialogs — never say "first appeal".
        return "Клиент обращался ранее; краткое описание сути пока недоступно."
    if len(cleaned) == 1:
        return _ensure_sentence(cleaned[0])
    # Compact multi-appeal blurb: at most two sentences.
    first = cleaned[0].rstrip(".!?…")
    second = cleaned[1].rstrip(".!?…")
    return (
        f"{_ensure_sentence(f'Ранее: {first}')} "
        f"{_ensure_sentence(f'Также: {second}')}"
    )


def prefetch_dialogs_for_summary(dialogs: list[Dialog]) -> list[Dialog]:
    if not dialogs:
        return dialogs
    ids = [item.id for item in dialogs]
    loaded = {
        item.id: item
        for item in Dialog.objects.filter(id__in=ids).prefetch_related(
            Prefetch(
                "messages",
                queryset=DialogMessage.objects.filter(is_deleted=False).order_by(
                    "created_at"
                ),
            )
        )
    }
    return [loaded.get(item.id, item) for item in dialogs]


def build_history_summaries(previous_dialogs: list[Dialog]) -> dict[str, Any]:
    """Return short text + structured detailed blocks for previous dialogs."""
    if not previous_dialogs:
        return {
            "summary": "Первое обращение клиента.",
            "detailed_summary": "Первое обращение клиента.",
            "summary_topics": [],
            "detailed_blocks": [],
            "is_first": True,
        }

    dialogs = prefetch_dialogs_for_summary(list(previous_dialogs[:6]))
    short_parts: list[str] = []
    blocks: list[dict[str, Any]] = []
    topics: list[str] = []

    for dialog in dialogs:
        try:
            ensure_dialog_summaries(dialog)
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "dialog_summary_ensure_failed dialog_id=%s error=%s",
                dialog.id,
                exc,
            )
        short = (dialog.summary_short or "").strip()
        detailed = (dialog.summary_detailed or "").strip() or short
        if not short:
            preview = (dialog.preview or "").strip()
            short = (
                f"Клиент обращался по вопросу: {preview[:140]}."
                if preview
                else "Клиент обращался ранее по банковскому вопросу."
            )
            detailed = short
        short_parts.append(short)
        topic = (dialog.close_topic or "").strip() or "Прочее"
        if topic not in topics:
            topics.append(topic)
        try:
            from django.utils import timezone as dj_tz

            date_label = dj_tz.localtime(dialog.created_at).strftime("%d.%m.%Y %H:%M")
        except Exception:  # noqa: BLE001
            date_label = dialog.created_at.isoformat()
        blocks.append(
            {
                "date_label": date_label,
                "topic": topic,
                "essence": detailed,
                "channel": dialog.channel or "",
                "operator_name": dialog.operator_name or "не назначен",
            }
        )

    summary = combine_short_summaries(short_parts)
    detailed_text_parts = []
    for block in blocks:
        detailed_text_parts.append(
            f"{block['date_label']}\n"
            f"Тема: {block['topic']}\n"
            f"{block['essence']}\n"
            f"Канал: {block['channel']} · Оператор: {block['operator_name']}"
        )
    return {
        "summary": summary,
        "detailed_summary": "\n\n".join(detailed_text_parts),
        "summary_topics": topics[:5],
        "detailed_blocks": blocks,
        "is_first": False,
    }
