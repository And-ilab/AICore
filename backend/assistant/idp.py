"""IDP for chat attachments: split a document into fragments and summarize (§5.1.38)."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from ingest.pipeline import chunk_text

IDP_CHUNK_WORDS = 220
IDP_CHUNK_OVERLAP = 40
IDP_MAX_FRAGMENTS_SUMMARY = 14
IDP_MAX_FRAGMENTS_QA = 8

_SUMMARIZE_RE = re.compile(
    r"суммариз|саммари|кратк(ое|ий)?\s+(резюме|обзор|пересказ)|"
    r"сделай\s+резюме|о чём\s+(файл|документ|запись)|содержим",
    re.I,
)
_MEDIA_TYPES = frozenset(
    {
        "wav",
        "mp3",
        "m4a",
        "aac",
        "ogg",
        "oga",
        "flac",
        "wma",
        "mp4",
        "mov",
        "mkv",
        "webm",
        "avi",
        "m4v",
        "audio",
        "video",
    }
)
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9]{3,}")

ATTACHMENT_MARKER = "[Вложение"

SUMMARY_INSTRUCTION = (
    "Задача IDP: документ разбит на фрагменты. "
    "Сделай связное текстовое резюме всего файла: о чём документ, "
    "ключевые условия, лимиты, документы и шаги. "
    "Заканчивай законченным предложением и законченной мыслью, "
    "не обрывай фразу или список. Не используй общую базу знаний."
)
SUMMARY_INSTRUCTION_MEDIA = (
    "Задача IDP: это транскрипт аудио или видео, разбитый на фрагменты. "
    "Сделай связное резюме записи: о чём речь, ключевые факты, "
    "решения и договорённости. "
    "Заканчивай законченным предложением и законченной мыслью. "
    "Не используй общую базу знаний."
)
QA_INSTRUCTION = (
    "Задача IDP: ответь на вопрос пользователя ТОЛЬКО по фрагментам "
    "загруженного документа. Если факта нет во фрагментах — так и скажи. "
    "Не подмешивай статьи из базы знаний."
)


def wants_summary(query: str) -> bool:
    text = (query or "").strip()
    if not text:
        return True
    if text.casefold().startswith("суммаризируй"):
        return True
    return bool(_SUMMARIZE_RE.search(text))


def has_attachment_marker(messages: Sequence[Mapping[str, Any]]) -> bool:
    return any(
        ATTACHMENT_MARKER in str(item.get("content") or "") for item in messages
    )


def split_fragments(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    words = cleaned.split()
    if len(words) <= IDP_CHUNK_WORDS:
        return [cleaned]
    return chunk_text(
        cleaned,
        chunk_size=IDP_CHUNK_WORDS,
        overlap=IDP_CHUNK_OVERLAP,
    )


def _score_fragment(fragment: str, query: str) -> int:
    needles = {token.casefold() for token in _TOKEN_RE.findall(query)}
    if not needles:
        return 0
    hay = fragment.casefold()
    return sum(1 for token in needles if token in hay)


def select_fragments(fragments: list[str], query: str, *, summarize: bool) -> list[str]:
    if not fragments:
        return []
    if summarize:
        return fragments[:IDP_MAX_FRAGMENTS_SUMMARY]
    ranked = sorted(
        enumerate(fragments),
        key=lambda item: (-_score_fragment(item[1], query), item[0]),
    )
    picked = [item[1] for item in ranked[:IDP_MAX_FRAGMENTS_QA]]
    # Keep reading order for the model.
    order = {frag: index for index, frag in enumerate(fragments)}
    return sorted(picked, key=lambda frag: order.get(frag, 0))


def build_attachment_prompt(
    attachments: Sequence[Mapping[str, Any]],
    query: str,
) -> str:
    summarize = wants_summary(query)
    blocks: list[str] = []
    has_media = False
    for index, item in enumerate(attachments):
        name = str(item.get("name") or item.get("filename") or f"file-{index}")
        kind = str(item.get("type") or item.get("content_type") or "file")
        media = item.get("media") if isinstance(item.get("media"), Mapping) else None
        is_media_item = bool(media) or kind.casefold() in _MEDIA_TYPES
        if is_media_item:
            has_media = True
        text = str(item.get("text") or item.get("extracted_text") or "").strip()
        fragments = select_fragments(
            split_fragments(text),
            query,
            summarize=summarize,
        )
        if not fragments:
            continue
        numbered = "\n\n".join(
            f"Фрагмент {number}/{len(fragments)}:\n{body}"
            for number, body in enumerate(fragments, start=1)
        )
        blocks.append(
            f"{ATTACHMENT_MARKER} «{name}» ({kind}) — "
            f"{'саммаризация' if summarize else ('ответ по записи' if is_media_item else 'ответ по документу')}]\n"
            f"{numbered}"
        )
    if not blocks:
        return ""
    if summarize and has_media:
        header = SUMMARY_INSTRUCTION_MEDIA
    elif summarize:
        header = SUMMARY_INSTRUCTION
    else:
        header = QA_INSTRUCTION
    return f"{header}\n\n" + "\n\n".join(blocks)
