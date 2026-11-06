"""Assistant topic filters (§5.1.15): dictionary gate plus a prompt clause.

The sufler and the online chat do not read this catalog. A dictionary hit
refuses before retrieval. A silent dictionary still adds the enabled topic
names and their refusal phrases to the assistant system prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from django.db import transaction

from hub.models import AssistantContentFilter

logger = logging.getLogger(__name__)

_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_WORD_EXTRA = r"[а-яь]{0,6}"
MAX_ITEMS = 30
MAX_PHRASES = 40

DEFAULT_REFUSAL = (
    "Не могу ответить на этот запрос: тема ограничена фильтром контента."
)

DEFAULT_CONTENT_FILTERS: tuple[dict[str, Any], ...] = (
    {
        "code": "politics",
        "name": "Политика",
        "enabled": True,
        "sort_order": 10,
        "keywords": [
            "политическ",
            "политик",
            "предвыбор",
            "депутат",
            "оппозиц",
            "избирательн",
            "парламент",
            "митинг",
            "выборы",
            "выборн",
            "голосован",
        ],
        "exceptions": [
            "политика банка",
            "тарифная политика",
            "кредитная политика",
            "учетная политика",
            "кадровая политика",
            "дивидендная политика",
            "процентная политика",
            "рисковая политика",
            "клиентская политика",
            "внутренняя политика",
        ],
        "refusal_text": (
            "Не могу ответить на этот запрос: тема ограничена фильтром "
            "контента «Политика»."
        ),
    },
    {
        "code": "religion",
        "name": "Религия",
        "enabled": True,
        "sort_order": 20,
        "keywords": [
            "религи",
            "церков",
            "молитв",
            "ислам",
            "христиан",
            "иудаизм",
            "буддизм",
            "мечет",
            "аллах",
            "бог",
            "бога",
            "богу",
            "богом",
            "боги",
            "богов",
        ],
        "exceptions": [],
        "refusal_text": (
            "Не могу ответить на этот запрос: тема ограничена фильтром "
            "контента «Религия»."
        ),
    },
)


class ContentFilterError(ValueError):
    """Invalid catalog payload. ``details`` matches the admin API shape."""

    def __init__(self, details: dict[str, list[str]]):
        self.details = details
        super().__init__("validation_error")


@dataclass(frozen=True)
class ContentFilterHit:
    code: str
    name: str
    refusal_text: str


def seed_default_content_filters(*, username: str = "system") -> None:
    for item in DEFAULT_CONTENT_FILTERS:
        AssistantContentFilter.objects.get_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "enabled": item["enabled"],
                "keywords": list(item["keywords"]),
                "exceptions": list(item["exceptions"]),
                "refusal_text": item["refusal_text"],
                "sort_order": item["sort_order"],
                "updated_by": username,
            },
        )


def list_content_filters() -> list[AssistantContentFilter]:
    return list(AssistantContentFilter.objects.all())


def serialize_content_filter(item: AssistantContentFilter) -> dict[str, Any]:
    return {
        "id": item.pk,
        "code": item.code,
        "name": item.name,
        "enabled": bool(item.enabled),
        "keywords": _string_list(item.keywords),
        "exceptions": _string_list(item.exceptions),
        "refusal_text": item.refusal_text,
        "sort_order": item.sort_order,
        "updated_at": item.updated_at.isoformat() if item.updated_at else "",
        "updated_by": item.updated_by,
    }


def serialize_content_filters() -> dict[str, Any]:
    return {"items": [serialize_content_filter(item) for item in list_content_filters()]}


@transaction.atomic
def replace_content_filters(
    items: Sequence[Mapping[str, Any]],
    *,
    username: str,
) -> dict[str, Any]:
    parsed = _parse_items(items)
    codes = [item["code"] for item in parsed]
    AssistantContentFilter.objects.exclude(code__in=codes).delete()
    for item in parsed:
        AssistantContentFilter.objects.update_or_create(
            code=item["code"],
            defaults={
                "name": item["name"],
                "enabled": item["enabled"],
                "keywords": item["keywords"],
                "exceptions": item["exceptions"],
                "refusal_text": item["refusal_text"],
                "sort_order": item["sort_order"],
                "updated_by": username,
            },
        )
    return serialize_content_filters()


def match_content_filter(text: str) -> ContentFilterHit | None:
    """Return the first enabled category whose dictionary matches ``text``."""
    normalized = _normalize(text)
    if not normalized:
        return None
    for item in list_content_filters():
        if not item.enabled:
            continue
        masked = _mask_exceptions(normalized, _string_list(item.exceptions))
        for keyword in _string_list(item.keywords):
            if _keyword_matches(masked, keyword):
                return ContentFilterHit(
                    code=item.code,
                    name=item.name,
                    refusal_text=item.refusal_text.strip() or DEFAULT_REFUSAL,
                )
    return None


def content_filter_instruction() -> str:
    """Short system-prompt clause. Empty when every category is off."""
    enabled = [item for item in list_content_filters() if item.enabled]
    if not enabled:
        return ""
    lines = [
        "Фильтры контента. Если запрос относится к одной из тем ниже, "
        "не используй базу знаний и не отвечай по существу. "
        "Ответь только указанной фразой отказа для этой темы.",
        "Служебные вопросы банка (кредитная, тарифная, кадровая, учётная "
        "политика банка) к этим темам не относятся.",
    ]
    for item in enabled:
        refusal = (item.refusal_text or DEFAULT_REFUSAL).strip()
        lines.append(f"- {item.name}: {refusal}")
    return "\n".join(lines)


def apply_content_filter_instruction(
    messages: Sequence[Mapping[str, str]],
) -> list[dict[str, str]]:
    clause = ""
    try:
        clause = content_filter_instruction()
    except Exception:
        logger.exception("content_filter_instruction_failed")
    copied = [
        {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")}
        for item in messages
    ]
    if not clause:
        return copied
    for item in copied:
        if item["role"] == "system":
            item["content"] = f"{item['content']}\n\n{clause}"
            return copied
    return [{"role": "system", "content": clause}, *copied]


def audit_content_filter_block(*, username: str, code: str) -> None:
    """Journal a dictionary refusal. The user text is not stored."""
    from audit.events import (
        ASSISTANT_CONTENT_FILTER_BLOCKED,
        CATEGORY_DATA_SECURITY,
        RESULT_SUCCESS,
    )
    from audit.schema import AuditSubject
    from audit.service import emit

    emit(
        category=CATEGORY_DATA_SECURITY,
        event_type=ASSISTANT_CONTENT_FILTER_BLOCKED,
        result=RESULT_SUCCESS,
        subject=AuditSubject(user_login=username or "anonymous"),
        module="assistant",
        description="Assistant request blocked by a content filter",
        severity="medium",
        details={"category": code},
    )


def audit_content_filter_update(*, request: Any, codes: Sequence[str]) -> None:
    from audit.events import (
        ASSISTANT_CONTENT_FILTER_UPDATED,
        CATEGORY_ADMINISTRATION,
        RESULT_SUCCESS,
    )
    from audit.service import emit, request_context, subject_from_request

    emit(
        category=CATEGORY_ADMINISTRATION,
        event_type=ASSISTANT_CONTENT_FILTER_UPDATED,
        result=RESULT_SUCCESS,
        subject=subject_from_request(request),
        module="hub",
        description="Assistant content filters updated",
        request=request_context(request),
        details={"categories": list(codes)},
    )


def _parse_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(items, (str, bytes)) or not isinstance(items, Sequence):
        raise ContentFilterError({"items": ["Ожидается список категорий."]})
    if len(items) > MAX_ITEMS:
        raise ContentFilterError(
            {"items": [f"Не больше {MAX_ITEMS} категорий."]}
        )
    parsed: list[dict[str, Any]] = []
    details: dict[str, list[str]] = {}
    seen: set[str] = set()
    for index, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            details[f"items.{index}"] = ["Категория должна быть объектом."]
            continue
        item, item_errors = _parse_item(raw, index)
        details.update(item_errors)
        if item is None:
            continue
        if item["code"] in seen:
            details.setdefault(f"items.{index}.code", []).append(
                "Код категории повторяется."
            )
        seen.add(item["code"])
        parsed.append(item)
    if details:
        raise ContentFilterError(details)
    return parsed


def _parse_item(
    raw: Mapping[str, Any],
    index: int,
) -> tuple[dict[str, Any] | None, dict[str, list[str]]]:
    errors: dict[str, list[str]] = {}
    prefix = f"items.{index}"

    code = str(raw.get("code") or "").strip().lower()
    if not _CODE_RE.fullmatch(code):
        errors[f"{prefix}.code"] = [
            "Код: латиница, цифры и _, с буквы, до 32 символов."
        ]

    name = str(raw.get("name") or "").strip()
    if not name or len(name) > 80:
        errors[f"{prefix}.name"] = ["Название: от 1 до 80 символов."]

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        errors[f"{prefix}.enabled"] = ["Поле enabled должно быть true или false."]
        enabled = True

    keywords, keyword_error = _parse_phrases(raw.get("keywords"), label="слово")
    if keyword_error:
        errors[f"{prefix}.keywords"] = [keyword_error]
    elif enabled and not keywords:
        errors[f"{prefix}.keywords"] = [
            "У включённой категории нужно хотя бы одно слово или фраза."
        ]

    exceptions, exception_error = _parse_phrases(
        raw.get("exceptions", []),
        label="исключение",
        allow_empty_items=True,
    )
    if exception_error:
        errors[f"{prefix}.exceptions"] = [exception_error]

    refusal = str(raw.get("refusal_text") or "").strip()
    if not refusal or len(refusal) > 500:
        errors[f"{prefix}.refusal_text"] = ["Текст отказа: от 1 до 500 символов."]

    sort_order = raw.get("sort_order", index * 10)
    if isinstance(sort_order, bool) or not isinstance(sort_order, int):
        errors[f"{prefix}.sort_order"] = ["Порядок должен быть целым числом."]
        sort_order = index * 10
    elif not 0 <= sort_order <= 10000:
        errors[f"{prefix}.sort_order"] = ["Порядок должен быть от 0 до 10000."]

    if errors:
        return None, errors
    return (
        {
            "code": code,
            "name": name,
            "enabled": enabled,
            "keywords": keywords,
            "exceptions": exceptions,
            "refusal_text": refusal,
            "sort_order": sort_order,
        },
        {},
    )


def _parse_phrases(
    raw: Any,
    *,
    label: str,
    allow_empty_items: bool = False,
) -> tuple[list[str], str]:
    if raw is None and allow_empty_items:
        return [], ""
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        return [], f"Список ({label}) должен быть массивом строк."
    if len(raw) > MAX_PHRASES:
        return [], f"Не больше {MAX_PHRASES} значений."
    phrases: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return [], f"Каждое {label} должно быть строкой."
        phrase = " ".join(item.split())
        if not phrase:
            continue
        if len(phrase) < 2 or len(phrase) > 120:
            return [], f"Каждое {label}: от 2 до 120 символов."
        phrases.append(phrase)
    return phrases, ""


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _normalize(text: str) -> str:
    return (text or "").casefold().replace("ё", "е")


def _phrase_stems(phrase: str) -> list[str]:
    stems: list[str] = []
    for word in re.findall(r"[0-9a-zа-я]+", _normalize(phrase)):
        if len(word) < 4:
            continue
        stems.append(word if len(word) <= 5 else word[:5])
    return stems


def _mask_exceptions(text: str, exceptions: Sequence[str]) -> str:
    masked = text
    phrases = sorted(
        (_normalize(item).strip() for item in exceptions),
        key=len,
        reverse=True,
    )
    for phrase in phrases:
        if len(phrase) < 3:
            continue
        masked = masked.replace(phrase, " " * len(phrase))
        stems = _phrase_stems(phrase)
        if len(stems) < 2:
            continue
        pattern = r"(?<![\w])" + r"\W+".join(
            rf"{re.escape(stem)}[\w]*" for stem in stems
        )
        masked = re.sub(pattern, lambda match: " " * len(match.group(0)), masked)
    return masked


def _keyword_matches(text: str, keyword: str) -> bool:
    needle = _normalize(keyword).strip()
    if len(needle) < 2:
        return False
    if len(needle) < 5:
        pattern = rf"(?<![\w]){re.escape(needle)}(?![\w])"
    else:
        pattern = rf"(?<![\w]){re.escape(needle)}{_WORD_EXTRA}(?![\w])"
    return re.search(pattern, text) is not None
