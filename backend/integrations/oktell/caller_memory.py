"""Remember one short client question per real phone number.

A placeholder such as ``sufler`` is not a phone, so those calls are not stored
and are not glued together.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PLACEHOLDERS = {"sufler", "live", "anonymous", "unknown", "hidden", "unavailable"}


def real_caller_phone(raw: str) -> str:
    from online_chat.models import normalize_phone

    cleaned = (raw or "").strip()
    if not cleaned or cleaned.casefold() in _PLACEHOLDERS:
        return ""
    phone = normalize_phone(cleaned)
    digits = re.sub(r"\D+", "", phone)
    if len(digits) < 6:
        return ""
    return phone


def previous_call(raw_phone: str) -> tuple[str, str]:
    """Question and ISO time saved from an earlier call, or empty strings."""
    phone = real_caller_phone(raw_phone)
    if not phone:
        return "", ""
    try:
        from hub.models import TelephonyCallerMemory

        row = TelephonyCallerMemory.objects.filter(phone=phone).first()
    except Exception:
        logger.debug("previous call lookup failed", exc_info=True)
        return "", ""
    if row is None:
        return "", ""
    asked = row.asked_at.isoformat() if row.asked_at else ""
    return (row.question or "").strip(), asked


def remember_client_question(raw_phone: str, text: str) -> None:
    phone = real_caller_phone(raw_phone)
    question = " ".join((text or "").split())[:240]
    if not phone or len(question) < 8:
        return
    if not re.search(r"[A-Za-zА-Яа-яЁё]", question):
        return
    try:
        from hub.models import TelephonyCallerMemory

        TelephonyCallerMemory.objects.update_or_create(
            phone=phone,
            defaults={"question": question},
        )
    except Exception:
        logger.debug("could not store caller question", exc_info=True)
