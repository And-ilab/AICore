from __future__ import annotations

import json
import re
from typing import Any

from core.model_gateway import ModelGateway
from hub.model_registry_store import get_model_settings
from online_chat.models import DialogCloseTopicNode

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-Я0-9]{3,}")


def _tokens(text: str) -> set[str]:
    return {match.group(0).lower() for match in _TOKEN_RE.finditer(text or "")}


def topic_tree(active_only: bool = True) -> list[dict[str, Any]]:
    qs = DialogCloseTopicNode.objects.all().order_by("sort_order", "label")
    if active_only:
        qs = qs.filter(is_active=True)
    items = list(qs)
    by_parent: dict[str | None, list[DialogCloseTopicNode]] = {}
    for item in items:
        key = str(item.parent_id) if item.parent_id else None
        by_parent.setdefault(key, []).append(item)

    def build(parent_id: str | None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for node in by_parent.get(parent_id, []):
            children = build(str(node.id))
            rows.append(
                {
                    "id": str(node.id),
                    "parent_id": str(node.parent_id) if node.parent_id else None,
                    "label": node.label,
                    "full_path": node.full_path or node.label,
                    "sort_order": node.sort_order,
                    "is_active": node.is_active,
                    "is_selectable": node.is_selectable,
                    "children": children,
                }
            )
        return rows

    return build(None)


def selectable_topics(active_only: bool = True) -> list[DialogCloseTopicNode]:
    qs = DialogCloseTopicNode.objects.filter(is_selectable=True).order_by("sort_order", "label")
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs)


def rebuild_full_paths() -> None:
    items = list(DialogCloseTopicNode.objects.all().order_by("sort_order", "label"))
    by_id = {item.id: item for item in items}
    by_parent: dict[Any, list[DialogCloseTopicNode]] = {}
    for item in items:
        by_parent.setdefault(item.parent_id, []).append(item)

    def visit(node: DialogCloseTopicNode, prefix: str = "") -> None:
        path = f"{prefix} / {node.label}".strip(" /") if prefix else node.label.strip()
        if node.full_path != path:
            node.full_path = path
            node.save(update_fields=["full_path", "updated_at"])
        for child in by_parent.get(node.id, []):
            visit(child, path)

    for root in by_parent.get(None, []):
        visit(root, "")

    # Guard invalid parent references after deletes/edits.
    for item in items:
        if item.parent_id and item.parent_id not in by_id:
            item.parent = None
            item.full_path = item.label.strip()
            item.save(update_fields=["parent", "full_path", "updated_at"])


def classify_by_titles(article_titles: list[str]) -> dict[str, Any]:
    """Ask the LLM to pick the closest closing topic given SUZ article titles.

    The candidate list is always the *full*, flat set of currently selectable
    topics (leaf "темы", never group "вложения") straight from the DB, so
    whatever an admin adds/removes in the topics panel is reflected on the
    very next call — no caching, no pre-filtering that could hide the right
    answer from the model.
    """
    cleaned_titles = [title.strip() for title in article_titles if isinstance(title, str) and title.strip()]
    candidates = selectable_topics(active_only=True)
    if not cleaned_titles or not candidates:
        return {"topic_id": None, "topic_path": "", "confidence": 0.0}

    # Only used as a last-resort fallback if the LLM response can't be
    # matched to a real candidate id (e.g. malformed JSON, network error).
    title_tokens = _tokens(" ".join(cleaned_titles))
    scored = sorted(
        candidates,
        key=lambda topic: len(title_tokens.intersection(_tokens(topic.full_path or topic.label))),
        reverse=True,
    )

    choices = [{"id": str(topic.id), "path": topic.full_path} for topic in candidates]
    message = {
        "article_titles": cleaned_titles[:12],
        "candidate_topics": choices,
        "task": (
            "Выбери одну тему закрытия диалога из полного списка candidate_topics, которая лучше всего "
            "соответствует совокупной теме по названиям статей СУЗ. Верни только JSON формата "
            '{"topic_id":"...", "confidence":0.0}.'
        ),
    }
    raw = ""
    try:
        settings = get_model_settings("sufler_cc")
        gateway = ModelGateway.from_registry()
        response = gateway.chat(
            "sufler_cc",
            [
                {
                    "role": "system",
                    "content": (
                        "Ты классификатор темы диалога КЦ. Выбирай только topic_id из списка candidate_topics. "
                        "Если уверенность низкая, верни confidence < 0.55. Ответ строго JSON."
                    ),
                },
                {"role": "user", "content": json.dumps(message, ensure_ascii=False)},
            ],
            temperature=0.0,
            top_p=float(settings.top_p),
            max_tokens=180,
        )
        # `gateway.chat` returns the full OpenAI-compatible completion object,
        # not the raw text — the actual model reply lives at
        # choices[0].message.content. Feeding the dict itself to json.loads
        # always raised (silently), so the LLM pick was never applied and the
        # code fell back to the lexical-overlap heuristic on every call.
        raw = str(response["choices"][0]["message"]["content"] or "")
    except Exception:
        raw = ""
    parsed_id = ""
    confidence = 0.0
    try:
        payload = json.loads(raw)
        parsed_id = str(payload.get("topic_id") or "").strip()
        confidence = float(payload.get("confidence") or 0.0)
    except Exception:
        parsed_id = ""
        confidence = 0.0

    picked = next((topic for topic in candidates if str(topic.id) == parsed_id), None)
    if picked is None:
        # Fallback: best lexical overlap across the full candidate set.
        picked = scored[0]
        confidence = max(confidence, 0.4)
    return {
        "topic_id": str(picked.id),
        "topic_path": picked.full_path,
        "confidence": max(0.0, min(1.0, confidence)),
    }
