"""Telegram intake FSM driven by channel form_fields and required flags."""

from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

from online_chat.channel_delivery import send_telegram_text
from online_chat.models import (
    ChannelConnection,
    Dialog,
    DialogMessage,
    TelegramOnboardingSession,
    format_phone_e164,
    is_plausible_phone,
    normalize_form_fields,
)
from online_chat.services import append_message, create_dialog_with_message


GREETING = (
    "Здравствуйте! Вы написали в службу поддержки Беларусбанка.\n\n"
    "Опишите, пожалуйста, ваш вопрос одним сообщением."
)
ASK_FIO = "Спасибо. Укажите, пожалуйста, ваше ФИО (фамилия и имя)."
ASK_PHONE = (
    "Укажите номер телефона для связи (можно с кодом страны).\n"
    "Примеры: +375291234567, 80291234567, +491701234567"
)
INVALID_FIO = "Не удалось разобрать ФИО. Укажите фамилию и имя, например: Иванов Иван."
INVALID_PHONE = (
    "Не удалось распознать номер. Введите телефон цифрами, "
    "можно с «+» и кодом страны."
)
QUEUED = (
    "Спасибо! Ваше обращение передано оператору. "
    "Ожидайте ответа в этом чате."
)

# Internal steps after question.
STEP_COLLECT = "collect_fields"
FIELD_PROMPTS = {
    "name": "Укажите, пожалуйста, ваше имя.",
    "first_name": "Укажите, пожалуйста, ваше имя.",
    "last_name": "Укажите, пожалуйста, вашу фамилию.",
    "phone": ASK_PHONE,
    "email": "Укажите, пожалуйста, ваш email.",
    "question": "Опишите, пожалуйста, ваш вопрос одним сообщением.",
}


def _telegram_form_fields() -> list[dict[str, Any]]:
    """Resolve intake fields from Telegram channel config (fallback: name+phone)."""
    channel = (
        ChannelConnection.objects.filter(
            channel=ChannelConnection.Channel.TELEGRAM,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )
    raw: list[Any] = []
    if channel and isinstance(channel.config, dict):
        candidate = channel.config.get("form_fields")
        if isinstance(candidate, list) and candidate:
            raw = candidate
    if not raw:
        raw = [
            {"key": "name", "label": "Имя", "required": True, "type": "text"},
            {"key": "phone", "label": "Телефон", "required": True, "type": "tel"},
        ]
    return normalize_form_fields(raw, require_phone=False)


def _field_required(field: dict[str, Any]) -> bool:
    return bool(field.get("required"))


def _prompt_for_field(field: dict[str, Any]) -> str:
    key = field["key"]
    label = field.get("label") or key
    required = _field_required(field)
    if key in FIELD_PROMPTS:
        base = FIELD_PROMPTS[key]
    else:
        base = f"Укажите, пожалуйста: {label}."
    if required:
        return base
    return f"{base}\n\nПоле необязательное — можно пропустить кнопкой ниже."


_INVISIBLE_RE = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")


def _is_skip(raw: str) -> bool:
    value = (raw or "").strip().casefold()
    return value in {"-", "—", "пропустить", "skip", "нет", "не укажу", "не хочу"}


def _clean_text(raw: str) -> str:
    return _INVISIBLE_RE.sub("", raw or "").strip()


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Telegram entity offset/length are UTF-16 code units, not Python characters."""
    encoded = (text or "").encode("utf-16-le")
    start = max(int(offset), 0) * 2
    end = start + max(int(length), 0) * 2
    if start >= len(encoded) or end <= start:
        return ""
    return encoded[start : min(end, len(encoded))].decode("utf-16-le", errors="ignore")


def _bot_command(text: str, raw: Mapping[str, Any] | None = None) -> str:
    """Canonical command token ('/start') or empty if this is not a bot command."""
    payload = raw if isinstance(raw, Mapping) else {}
    message = payload.get("message") or payload.get("edited_message") or {}
    if not isinstance(message, Mapping):
        message = {}
    original = str(message.get("text") or message.get("caption") or text or "")
    entities = message.get("entities") or message.get("caption_entities") or []
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, Mapping):
                continue
            if str(ent.get("type") or "") != "bot_command":
                continue
            if int(ent.get("offset") or 0) != 0:
                continue
            token = _utf16_slice(original, 0, int(ent.get("length") or 0))
            token = _clean_text(token) or _clean_text(original).split(None, 1)[0]
            name = token.split("@", 1)[0].casefold()
            if name and not name.startswith("/"):
                name = f"/{name}"
            return name
    head = _clean_text(original or text).split(None, 1)[0].casefold() if (original or text) else ""
    head = head.replace("／", "/").replace("∕", "/")
    if head.startswith("/"):
        return head.split("@", 1)[0]
    return ""


def _start_token(raw: str) -> str:
    token = _clean_text(raw).split(None, 1)[0].casefold() if raw else ""
    token = token.replace("／", "/").replace("∕", "/")
    if token.startswith("/"):
        token = token[1:]
    return token.split("@", 1)[0]


def _is_start_command(command: str, text: str) -> bool:
    """Match /start, /start@bot, /start payload, start, начать."""
    return _start_token(command) in {"start", "начать"} or _start_token(text) in {
        "start",
        "начать",
    }


def _parse_fio(raw: str) -> tuple[str, str] | None:
    cleaned = re.sub(r"\s+", " ", (raw or "").strip())
    if len(cleaned) < 3:
        return None
    parts = cleaned.split(" ")
    if len(parts) < 2:
        return None
    last_name = parts[0][:100]
    first_name = " ".join(parts[1:])[:100]
    if not first_name or not last_name:
        return None
    return first_name, last_name


def _active_dialog(chat_id: str) -> Dialog | None:
    identity = str(chat_id or "").strip()
    if not identity or identity == "unknown":
        return None
    return (
        Dialog.objects.filter(
            channel="telegram",
            client_external_id=identity,
            status__in=(Dialog.Status.WAITING, Dialog.Status.ACTIVE),
        )
        .order_by("-updated_at")
        .first()
    )


def _live_dialog_for_session(
    session: TelegramOnboardingSession | None,
    chat_id: str,
) -> Dialog | None:
    """Only the dialog created by this completed intake — never a previous open chat."""
    if session is not None and session.step != TelegramOnboardingSession.Step.DONE:
        return None
    payload = _session_payload(session) if session is not None else {}
    if payload.get("detached"):
        return None
    existing = _active_dialog(chat_id)
    if existing is None:
        return None
    bound = str(payload.get("bound_dialog_id") or "").strip()
    if bound and bound != str(existing.id):
        return None
    return existing


def _reply(
    chat_id: str,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    send_telegram_text(chat_id, text, reply_markup=reply_markup)
    return {
        "ok": True,
        "channel": "telegram",
        "reply": {"method": "sendMessage", "chat_id": chat_id, "text": text},
        **extra,
    }


def _session_payload(session: TelegramOnboardingSession) -> dict[str, Any]:
    raw = session.meta if isinstance(getattr(session, "meta", None), dict) else {}
    return dict(raw or {})


def _save_payload(session: TelegramOnboardingSession, payload: dict[str, Any]) -> None:
    session.meta = payload
    session.save(update_fields=["meta", "updated_at"])


def _collect_client_fields(
    session: TelegramOnboardingSession,
    payload: Mapping[str, Any],
) -> list[dict[str, str]]:
    """Build an ordered {label, value} list from what the client entered."""
    values: dict[str, str] = {
        "name": f"{session.first_name} {session.last_name}".strip(),
        "first_name": session.first_name,
        "last_name": session.last_name,
        "phone": format_phone_e164(session.phone) or session.phone,
        "email": str(payload.get("email") or ""),
    }
    collected: list[dict[str, str]] = []
    seen_labels: set[str] = set()
    # Name and phone have dedicated rows in the ARM card — show only extras here.
    core_keys = {"question", "message", "name", "first_name", "last_name", "phone"}
    for field in _telegram_form_fields():
        key = field.get("key") or ""
        if key in core_keys:
            continue
        value = values.get(key)
        if value is None:
            value = str(payload.get(key) or "")
        value = str(value).strip()
        if not value:
            continue
        label = str(field.get("label") or key).strip() or key
        if label in seen_labels:
            continue
        seen_labels.add(label)
        collected.append({"label": label, "value": value})
    return collected


def _finish_dialog(session: TelegramOnboardingSession, chat_id: str) -> dict[str, Any]:
    phone = format_phone_e164(session.phone)
    question = session.question.strip() or "Обращение из Telegram"
    payload_now = _session_payload(session)
    client_fields = _collect_client_fields(session, payload_now)
    try:
        dialog, message = create_dialog_with_message(
            text=question,
            channel="telegram",
            widget_id="",
            placement="telegram",
            client_first_name=session.first_name,
            client_last_name=session.last_name,
            client_phone=phone,
            client_external_id=chat_id,
            client_fields=client_fields,
        )
    except PermissionError:
        return _reply(
            chat_id,
            "Ваш номер находится в списке блокировок. Обратитесь в отделение банка.",
            routed_to="blocked",
        )
    session.step = TelegramOnboardingSession.Step.DONE
    payload = _session_payload(session)
    payload["bound_dialog_id"] = str(dialog.id)
    payload["detached"] = False
    payload.pop("field_index", None)
    payload.pop("fields", None)
    session.meta = payload
    session.save(update_fields=["step", "meta", "updated_at"])
    return _reply(
        chat_id,
        QUEUED,
        routed_to="arm_queue",
        dialog_id=str(dialog.id),
        message_id=str(message.id),
        step=session.step,
    )


def _ask_next_field(
    session: TelegramOnboardingSession,
    chat_id: str,
    fields: list[dict[str, Any]],
    index: int,
) -> dict[str, Any]:
    payload = _session_payload(session)
    payload["field_index"] = index
    payload["fields"] = [field["key"] for field in fields]
    _save_payload(session, payload)
    if index >= len(fields):
        return _finish_dialog(session, chat_id)
    field = fields[index]
    required = _field_required(field)
    markup = None
    if not required:
        markup = {
            "inline_keyboard": [[{"text": "Пропустить", "callback_data": "skip_field"}]]
        }
    return _reply(
        chat_id,
        _prompt_for_field(field),
        reply_markup=markup,
        routed_to="onboarding",
        step=STEP_COLLECT,
        field=field["key"],
    )


def _begin_onboarding(chat_id: str) -> dict[str, Any]:
    """Reset intake and ask the user to describe the question."""
    session, _ = TelegramOnboardingSession.objects.get_or_create(
        chat_id=chat_id,
        defaults={"step": TelegramOnboardingSession.Step.AWAIT_QUESTION},
    )
    session.step = TelegramOnboardingSession.Step.AWAIT_QUESTION
    session.question = ""
    session.first_name = ""
    session.last_name = ""
    session.phone = ""
    session.save(
        update_fields=[
            "step",
            "question",
            "first_name",
            "last_name",
            "phone",
            "updated_at",
        ]
    )
    payload = _session_payload(session)
    payload.pop("field_index", None)
    payload.pop("fields", None)
    payload.pop("bound_dialog_id", None)
    payload["detached"] = True
    _save_payload(session, payload)
    return _reply(
        chat_id,
        GREETING,
        routed_to="onboarding",
        step=session.step,
    )


def handle_telegram_skip_field(*, chat_id: str) -> dict[str, Any]:
    """Skip the current optional onboarding field (inline button)."""
    chat_id = str(chat_id)
    session = (
        TelegramOnboardingSession.objects.filter(chat_id=chat_id)
        .exclude(step=TelegramOnboardingSession.Step.DONE)
        .order_by("-updated_at")
        .first()
    )
    if session is None:
        return {
            "ok": True,
            "channel": "telegram",
            "routed_to": "skip_ignored",
        }
    fields = _telegram_form_fields()
    payload = _session_payload(session)
    index = int(payload.get("field_index") or 0)
    if index >= len(fields):
        return _finish_dialog(session, chat_id)
    field = fields[index]
    if _field_required(field):
        return _reply(
            chat_id,
            "Это поле обязательное — укажите данные сообщением.",
            routed_to="onboarding",
            step=STEP_COLLECT,
            field=field["key"],
        )
    return _ask_next_field(session, chat_id, fields, index + 1)


def handle_telegram_client_text(
    *,
    chat_id: str,
    text: str,
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    """Process one inbound Telegram text update through onboarding or live dialog."""
    chat_id = str(chat_id)
    cleaned = _clean_text(text)
    if not cleaned:
        return _reply(chat_id, GREETING, routed_to="ignored")

    command = _bot_command(cleaned, raw)
    if _is_start_command(command, cleaned):
        return _begin_onboarding(chat_id)
    if command:
        return {
            "ok": True,
            "channel": "telegram",
            "routed_to": "command_ignored",
            "command": command,
        }

    session = (
        TelegramOnboardingSession.objects.filter(chat_id=chat_id)
        .order_by("-updated_at")
        .first()
    )

    existing = _live_dialog_for_session(session, chat_id)
    if existing:
        external_message_id = str(raw.get("update_id") or "")
        message = append_message(
            existing,
            speaker=DialogMessage.Speaker.CLIENT,
            text=cleaned,
            external_message_id=external_message_id,
        )
        return {
            "ok": True,
            "channel": "telegram",
            "routed_to": "arm_queue",
            "event_id": str(uuid.uuid4()),
            "dialog_id": str(existing.id),
            "message_id": str(message.id),
        }

    if session is None:
        session = TelegramOnboardingSession.objects.create(
            chat_id=chat_id,
            step=TelegramOnboardingSession.Step.AWAIT_QUESTION,
        )
        send_telegram_text(chat_id, GREETING)

    if session.step == TelegramOnboardingSession.Step.DONE:
        return _begin_onboarding(chat_id)

    fields = _telegram_form_fields()

    if session.step == TelegramOnboardingSession.Step.AWAIT_QUESTION:
        session.question = cleaned[:4000]
        session.step = TelegramOnboardingSession.Step.AWAIT_FIO
        session.save(update_fields=["question", "step", "updated_at"])
        return _ask_next_field(session, chat_id, fields, 0)

    # Dynamic field collection (also covers legacy AWAIT_FIO / AWAIT_PHONE).
    payload = _session_payload(session)
    index = int(payload.get("field_index") or 0)
    if index >= len(fields):
        index = 0
    field = fields[index]
    key = field["key"]
    required = _field_required(field)

    if not required and _is_skip(cleaned):
        return _ask_next_field(session, chat_id, fields, index + 1)

    if key in {"name", "first_name"}:
        # Accept single name or full FIO.
        parsed = _parse_fio(cleaned)
        if parsed:
            session.first_name, session.last_name = parsed
        else:
            session.first_name = cleaned[:100]
            if not session.last_name:
                session.last_name = ""
        session.save(update_fields=["first_name", "last_name", "updated_at"])
    elif key == "last_name":
        session.last_name = cleaned[:100]
        session.save(update_fields=["last_name", "updated_at"])
    elif key == "phone":
        if not is_plausible_phone(cleaned):
            return _reply(chat_id, INVALID_PHONE, routed_to="onboarding", step=STEP_COLLECT)
        session.phone = format_phone_e164(cleaned)
        session.save(update_fields=["phone", "updated_at"])
    elif key == "email":
        if "@" not in cleaned or "." not in cleaned.split("@")[-1]:
            return _reply(
                chat_id,
                "Не удалось распознать email. Пример: name@example.by",
                routed_to="onboarding",
                step=STEP_COLLECT,
            )
        payload["email"] = cleaned[:200]
        _save_payload(session, payload)
    else:
        payload[key] = cleaned[:500]
        _save_payload(session, payload)

    # Ensure we have at least some name before finish.
    if not session.first_name and key not in {"name", "first_name"}:
        # keep going
        pass

    return _ask_next_field(session, chat_id, fields, index + 1)
