"""Language guardrails for operator-visible and indexed text."""

from __future__ import annotations

import unicodedata


def is_ru_en_letter(character: str) -> bool:
    codepoint = ord(character)
    return (
        0x0041 <= codepoint <= 0x005A
        or 0x0061 <= codepoint <= 0x007A
        or 0x00C0 <= codepoint <= 0x024F
        or 0x0400 <= codepoint <= 0x052F
        or 0x1E00 <= codepoint <= 0x1EFF
    )


def safe_ru_en_text(text: str) -> str:
    """Return normalized text, or empty when another alphabet is present."""
    normalized = unicodedata.normalize("NFC", text or "")
    for character in normalized:
        if unicodedata.category(character).startswith("L") and not is_ru_en_letter(
            character
        ):
            return ""
    cleaned = "".join(
        character
        for character in normalized
        if not unicodedata.category(character).startswith("C")
        or character in {"\n", "\t"}
    )
    return cleaned.strip()
