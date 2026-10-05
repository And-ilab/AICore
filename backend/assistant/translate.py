"""RU↔EN text translation. Files are not accepted."""

from __future__ import annotations

from typing import Any, Mapping

DIRECTIONS = {
    "ru-en": ("русского", "английский", "RU", "EN"),
    "en-ru": ("английского", "русский", "EN", "RU"),
}


class TranslateError(ValueError):
    """Text could not be translated."""


def translate_text(text: str, direction: str) -> dict[str, str]:
    cleaned = (text or "").strip()
    if direction not in DIRECTIONS:
        raise TranslateError("Выберите направление: RU → EN или EN → RU")
    if not cleaned:
        raise TranslateError("Введите текст")
    if len(cleaned) > 4000:
        raise TranslateError("Слишком длинный текст")
    source_lang, target_lang, source_label, target_label = DIRECTIONS[direction]
    instruction = (
        f"Переведи текст с {source_lang} на {target_lang}. "
        "Верни только перевод, без кавычек и без пояснений."
    )
    translated = _complete(instruction, cleaned)
    if not translated:
        raise TranslateError("Перевод пустой")
    return {
        "direction": direction,
        "source_label": source_label,
        "target_label": target_label,
        "source": cleaned,
        "text": translated,
    }


def _complete(instruction: str, text: str) -> str:
    from core.model_gateway import ModelGateway, ModelGatewayError

    try:
        result = ModelGateway.from_registry().chat(
            "assistant_bank",
            [
                {"role": "system", "content": instruction},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
            max_tokens=1200,
        )
    except ModelGatewayError as exc:
        raise TranslateError("Не удалось перевести текст") from exc
    return _message_text(result)


def _message_text(result: Mapping[str, Any]) -> str:
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TranslateError("Не удалось перевести текст")
    message = choices[0].get("message") if isinstance(choices[0], Mapping) else None
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, str) or not content.strip():
        raise TranslateError("Не удалось перевести текст")
    return content.strip()
