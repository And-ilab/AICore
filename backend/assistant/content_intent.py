"""Match chat prompts to UC-ASS-06 text drafts and UC-ASS-07 slides/diagrams."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from assistant.doc_templates import draft_payload
from assistant.docgen import render_body
from hub.assistant_admin import AssistantAdminError
from hub.models import AssistantDocumentTemplate

IntentKind = Literal["text", "slides", "diagram"]

_TEXT_RE = re.compile(
    r"записк|справк|отч[её]т|докладн|инструкц|описани[ея]\s+процесс",
    re.IGNORECASE,
)
_SLIDE_RE = re.compile(r"презентац|слайд|\bppt\b", re.IGNORECASE)
_DIAGRAM_RE = re.compile(
    r"bpmn|диаграмм|блок-?схем|er[\s-]?диаграмм|архитектурн",
    re.IGNORECASE,
)
_TOPIC_RE = re.compile(
    r"(?:о|об|про|по теме|на тему)\s+(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_LEAD_RE = re.compile(
    r"^(подготовьте|подготовь|сделай(?:те)?|сгенерируй(?:те)?|"
    r"напиши(?:те)?|создай(?:те)?|нужна|нужен|нужно)\s+",
    re.IGNORECASE,
)

KIND_FORMATS: dict[IntentKind, tuple[str, ...]] = {
    "text": (AssistantDocumentTemplate.FORMAT_TXT,),
    "slides": (AssistantDocumentTemplate.FORMAT_PPTX,),
    "diagram": (
        AssistantDocumentTemplate.FORMAT_BPMN,
        AssistantDocumentTemplate.FORMAT_MMD,
    ),
}


def classify_prompt(message: str) -> IntentKind | None:
    text = (message or "").strip()
    if not text:
        return None
    if _SLIDE_RE.search(text):
        return "slides"
    if _DIAGRAM_RE.search(text):
        return "diagram"
    if _TEXT_RE.search(text):
        return "text"
    return None


def extract_topic(message: str) -> str:
    text = (message or "").strip()
    match = _TOPIC_RE.search(text)
    if match:
        topic = re.sub(r"\s+", " ", match.group(1)).strip(" .")
        prefix = match.group(0)[: match.start(1) - match.start()].strip()
        if prefix.lower() in {"о", "об", "про"}:
            return f"{prefix} {topic}".strip()
        return topic
    cleaned = _LEAD_RE.sub("", text)
    cleaned = _TEXT_RE.sub("", cleaned)
    cleaned = _SLIDE_RE.sub("", cleaned)
    cleaned = _DIAGRAM_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,;:")
    return cleaned or text


def fields_from_prompt(
    template: AssistantDocumentTemplate,
    message: str,
) -> dict[str, str]:
    topic = extract_topic(message)
    today = date.today().strftime("%d.%m.%Y")
    values: dict[str, str] = {}
    for item in template.fields or []:
        if not isinstance(item, dict):
            continue
        field_id = str(item.get("id") or "").strip()
        if not field_id:
            continue
        if field_id in {
            "subject",
            "topic",
            "title",
            "theme",
            "goal",
            "body_text",
            "entities",
        }:
            values[field_id] = topic
        elif field_id == "plan":
            values[field_id] = (
                f"1. Подготовить материалы по теме: {topic}\n"
                "2. Согласовать с руководителем\n"
                "3. Зафиксировать сроки и ответственных"
            )
        elif field_id == "conclusions":
            values[field_id] = f"Рекомендуется согласовать и утвердить: {topic}."
        elif field_id in {"full_name", "author"}:
            values[field_id] = "________"
        elif field_id == "department":
            values[field_id] = "________"
        elif field_id in {"memo_date", "date", "issue_date", "start_date"}:
            values[field_id] = today
        else:
            values[field_id] = topic
    return values


def match_template(kind: IntentKind, message: str) -> AssistantDocumentTemplate:
    formats = KIND_FORMATS[kind]
    queryset = AssistantDocumentTemplate.objects.filter(
        active=True,
        output_format__in=formats,
    )
    if not queryset.exists():
        raise AssistantAdminError("нет активного шаблона для этого запроса")
    lowered = message.casefold()
    scored: list[tuple[int, AssistantDocumentTemplate]] = []
    for item in queryset:
        score = 0
        name = item.name.casefold()
        if "запис" in lowered and "запис" in name:
            score += 4
        if "справк" in lowered and "справк" in name:
            score += 4
        if re.search(r"отч[её]т", lowered) and re.search(r"отч[её]т", name):
            score += 4
        if "bpmn" in lowered and item.output_format == AssistantDocumentTemplate.FORMAT_BPMN:
            score += 5
        if "er" in lowered and item.output_format == AssistantDocumentTemplate.FORMAT_MMD:
            score += 5
        if "презентац" in lowered and item.output_format == AssistantDocumentTemplate.FORMAT_PPTX:
            score += 3
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return scored[0][1]


def generate_from_prompt(message: str) -> dict[str, Any]:
    kind = classify_prompt(message)
    if kind is None:
        raise AssistantAdminError("запрос не похож на записку, справку, презентацию или диаграмму")
    template = match_template(kind, message)
    values = fields_from_prompt(template, message)
    payload = draft_payload(template, values, strict=False)
    payload["kind"] = kind
    payload["fields"] = values
    payload["text"] = render_body(template, values, strict=False)
    return payload
