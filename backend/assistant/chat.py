"""Assistant chat orchestration: RAG over assistant_* → ModelGateway stream."""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from typing import Any, Iterator, Mapping, Sequence

from core.embeddings import embedding_backend_info
from core.model_gateway import ModelGateway, ModelGatewayConfigurationError
from hub.content_filters import (
    apply_content_filter_instruction,
    audit_content_filter_block,
    match_content_filter,
)
from hub.model_registry_store import get_model_settings
from assistant.idp import (
    build_attachment_prompt,
    has_attachment_marker,
    wants_summary,
)
from assistant.path_log import elapsed_ms, log_path
from qu.assistant_retrieval import preview_assistant_query
from hub.skill_store import apply_skill_layer

logger = logging.getLogger(__name__)

PROFILE = "assistant_bank"
_ATTACHMENT_MARKER = "[Вложение"
_ANSWER_STYLE = (
    "Пиши обычным текстом, без markdown (без **, *, заголовков #). "
    "Не перечисляй источники в тексте, не пиши «Источники:», номера [1] "
    "и фразы вроде «по предоставленным фрагментам» или «в базе знаний "
    "найдено» — источники уже показаны отдельно."
)
DEFAULT_SYSTEM_PROMPT = (
    "Ты внутренний ИИ-ассистент банка. Отвечай по подтверждённым "
    "корпоративным источникам, по делу. "
    "Заканчивай законченным предложением и законченной мыслью. "
    + _ANSWER_STYLE
)
_NO_KB_RULE = (
    "Запрещено использовать общие знания, догадки и информацию вне "
    "фрагментов. Не придумывай процедуры, сроки и правила. "
    "Если фрагменты по теме вопроса есть — ответь по ним, даже если "
    "формулировка не дословная. Если там перечислены кому платят, "
    "в каких случаях, размеры или как оформить — перескажи это. "
    "Скажи, что в базе знаний нет информации, только если фрагменты "
    "про другое и ответа там нет. Не пиши «во фрагментах не указано», "
    "если такие факты в тексте есть."
)
GROUNDED_SYSTEM_PROMPT = (
    "Ты внутренний ИИ-ассистент банка. Отвечай ТОЛЬКО фактами из "
    "переданных фрагментов базы знаний. Внимательно читай каждый фрагмент "
    "целиком: числа, сроки и условия уже есть в тексте — перенеси их "
    "в ответ дословно (например «сроком на 5 лет», «3 месяца»). "
    "Не утверждай, что данных нет, если они явно указаны во фрагментах. "
    "Не выводи сроки и даты из названий файлов или URL. "
    "Если во фрагментах несколько разных сроков — ответь по документу, "
    "который прямо отвечает на вопрос пользователя, и не смешивай "
    "чужие условия. "
    + _NO_KB_RULE
    + " Ответ по делу: закончи законченным предложением и законченной "
    "мыслью, не обрывай фразу, список или абзац на середине. "
    "Не пиши пустой следующий номер шага."
    + _ANSWER_STYLE
)
EXPAND_SYSTEM_PROMPT = (
    "Ты внутренний ИИ-ассистент банка. Дай полный ответ только по фактам "
    "из переданных фрагментов: все условия, кому подходит, как оформить, "
    "лимиты и документы. Не обрывай текст на середине предложения. "
    "Числа и сроки бери дословно из фрагментов. "
    + _NO_KB_RULE
    + " "
    + _ANSWER_STYLE
)
NO_KB_ANSWER = (
    "В выбранных базах знаний нет информации по этому вопросу. "
    "Ответить могу только по статьям из базы знаний."
)
# Local llama often runs with -c 4096; five full .doc chunks overflow (~10k tokens).
DEFAULT_RAG_LIMIT = 5
# Per-chunk budget for the LLM (UI citations still use short snippet).
LLM_CHUNK_CHARS = 2800
# Soft cap for all RAG bodies combined (leaves room for system + question + answer).
LLM_RAG_TOTAL_CHARS = 7200
_DURATION_MARKERS = (
    "сроком на",
    "срок",
    "бессрочн",
    "месяц",
    "календарн",
    "дней",
    " лет",
    "года",
)


class AssistantChatError(ValueError):
    """Invalid assistant chat request."""


def _as_messages(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    raw_messages = payload.get("messages")
    single = payload.get("message")

    messages: list[dict[str, str]] = []
    if raw_messages is not None:
        if not isinstance(raw_messages, Sequence) or isinstance(
            raw_messages, (str, bytes)
        ):
            raise AssistantChatError("messages must be an array")
        for index, item in enumerate(raw_messages):
            if not isinstance(item, Mapping):
                raise AssistantChatError(
                    f"messages[{index}] must be an object"
                )
            role = item.get("role")
            content = item.get("content")
            if role not in {"system", "user", "assistant", "tool"}:
                raise AssistantChatError(
                    f"messages[{index}].role is invalid"
                )
            if not isinstance(content, str):
                raise AssistantChatError(
                    f"messages[{index}].content must be a string"
                )
            messages.append({"role": str(role), "content": content})

    if isinstance(single, str) and single.strip():
        messages.append({"role": "user", "content": single.strip()})

    if not messages:
        raise AssistantChatError(
            "Provide non-empty message or messages[]"
        )

    has_user = any(
        item["role"] == "user" and item["content"].strip()
        for item in messages
    )
    if not has_user:
        raise AssistantChatError("At least one user message is required")

    if not any(item["role"] == "system" for item in messages):
        messages = [
            {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
            *messages,
        ]
    return messages


def _parse_message_id(value: Any) -> str:
    """Optional client id shared with the feedback button. Empty is allowed."""
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise AssistantChatError("message_id must be a string")
    text = value.strip()
    if not text or len(text) > 64:
        raise AssistantChatError("message_id must be 1..64 characters")
    return text


def _parse_kb_slugs(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("kb_slugs")
    if raw is None:
        single = payload.get("kb_slug")
        if isinstance(single, str) and single.strip():
            return [single.strip()]
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise AssistantChatError("kb_slugs must be an array of strings")
    slugs: list[str] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise AssistantChatError(
                f"kb_slugs[{index}] must be a non-empty string"
            )
        slugs.append(item.strip())
    return slugs


def parse_chat_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise AssistantChatError("Request body must be a JSON object")

    attachments = payload.get("attachments")
    has_attachments = (
        isinstance(attachments, Sequence)
        and not isinstance(attachments, (str, bytes))
        and len(attachments) > 0
    )
    working: dict[str, Any] = dict(payload)
    message = working.get("message")
    if (
        has_attachments
        and (not isinstance(message, str) or not message.strip())
        and not working.get("messages")
    ):
        # Attachment-only send: still need a user turn for the LLM.
        working["message"] = "Суммаризируй вложение."

    messages = _as_messages(working)
    if attachments is not None:
        messages = _apply_attachments(messages, attachments)

    session_id = payload.get("session_id")
    if session_id is None:
        session_id = str(uuid.uuid4())
    elif not isinstance(session_id, str) or not session_id.strip():
        raise AssistantChatError("session_id must be a non-empty string")

    stream = payload.get("stream", True)
    if not isinstance(stream, bool):
        raise AssistantChatError("stream must be a boolean")
    if not stream:
        raise AssistantChatError(
            "Only stream=true is supported on POST /chat (SSE)"
        )

    expand = payload.get("expand", False)
    if not isinstance(expand, bool):
        raise AssistantChatError("expand must be a boolean")

    skill_id = payload.get("skill_id")
    if skill_id is not None:
        if isinstance(skill_id, bool) or not isinstance(skill_id, int):
            raise AssistantChatError("skill_id must be an integer")

    return {
        "messages": messages,
        "session_id": session_id.strip(),
        "stream": True,
        "kb_slugs": _parse_kb_slugs(payload),
        "expand": expand,
        "skill_id": skill_id,
        "message_id": _parse_message_id(payload.get("message_id")),
    }


def _apply_attachments(
    messages: list[dict[str, str]],
    attachments: Any,
) -> list[dict[str, str]]:
    """ASS-T-04/04a: fold attachment text into the last user message."""
    if not isinstance(attachments, Sequence) or isinstance(
        attachments, (str, bytes)
    ):
        raise AssistantChatError("attachments must be an array")
    for index, item in enumerate(attachments):
        if not isinstance(item, Mapping):
            raise AssistantChatError(f"attachments[{index}] must be an object")
        text = item.get("text") or item.get("extracted_text") or ""
        if not isinstance(text, str) or not text.strip():
            raise AssistantChatError(
                f"attachments[{index}] requires text/extracted_text "
                "(IDP summarization path)"
            )
    query = _last_user_text(messages)
    appendix = build_attachment_prompt(attachments, query)
    if not appendix:
        return messages
    for index in range(len(messages) - 1, -1, -1):
        if messages[index]["role"] == "user":
            messages[index] = {
                "role": "user",
                "content": f"{messages[index]['content']}\n\n{appendix}".strip(),
            }
            return messages
    messages.append({"role": "user", "content": appendix})
    return messages


def _last_user_text(messages: Sequence[Mapping[str, str]]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content") or "").strip()
    return ""


def _filter_query(messages: Sequence[Mapping[str, str]]) -> str:
    """User question only. Attachment fragments are not a content-filter subject."""
    text = _last_user_text(messages)
    marker_at = text.find(_ATTACHMENT_MARKER)
    if marker_at >= 0:
        text = text[:marker_at]
    return text.strip()


def _is_http_permalink(permalink: str) -> bool:
    return permalink.startswith("http://") or permalink.startswith("https://")


def _citation(document: Mapping[str, Any]) -> dict[str, Any]:
    kb_slug = str(document.get("kb_slug") or "")
    article_id = document.get("article_id")
    permalink = str(document.get("permalink") or "")
    # File chunks use the download API. Website pages keep their http(s) URL.
    if not _is_http_permalink(permalink) and kb_slug and article_id is not None:
        try:
            from hub.assistant_admin import assistant_source_download_url

            permalink = assistant_source_download_url(
                kb_slug=kb_slug,
                article_id=article_id,
            )
        except Exception:
            pass
    return {
        "id": (
            f"{kb_slug}:{article_id}:"
            f"{document.get('chunk_index')}"
        ),
        "kb_slug": kb_slug or document.get("kb_slug"),
        "article_id": article_id,
        "chunk_index": document["chunk_index"],
        "title": document["title"],
        "permalink": permalink,
        "snippet": document.get("snippet") or "",
        "relevance_percent": document.get("relevance_percent"),
    }


def _trim_text_for_llm(text: str, max_chars: int) -> str:
    """Fit chunk into local context; keep a window around duration clauses."""
    cleaned = text.strip()
    if max_chars <= 0 or not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned

    lower = cleaned.lower()
    marker_at = -1
    for marker in _DURATION_MARKERS:
        index = lower.find(marker)
        if index >= 0 and (marker_at < 0 or index < marker_at):
            marker_at = index

    if marker_at >= 0:
        # Keep ~1/3 before the marker so «Настоящее согласие дается сроком…» stays intact.
        start = max(0, marker_at - max_chars // 3)
        end = min(len(cleaned), start + max_chars)
        if end - start < max_chars:
            start = max(0, end - max_chars)
        piece = cleaned[start:end]
        prefix = "…" if start else ""
        suffix = "…" if end < len(cleaned) else ""
        return f"{prefix}{piece}{suffix}"

    return cleaned[:max_chars] + "…"


def _document_raw_text(document: Mapping[str, Any]) -> str:
    content = document.get("content")
    if isinstance(content, str) and content.strip():
        return content
    snippet = document.get("snippet")
    return snippet if isinstance(snippet, str) else ""


def _document_context_text(document: Mapping[str, Any], max_chars: int) -> str:
    """Chunk text for the LLM, capped to fit local llama context."""
    return _trim_text_for_llm(_document_raw_text(document), max_chars)


def _inject_rag_context(
    messages: Sequence[Mapping[str, str]],
    documents: Sequence[Mapping[str, Any]],
    *,
    expand: bool = False,
) -> list[dict[str, str]]:
    context_blocks = []
    remaining = 16000 if expand else LLM_RAG_TOTAL_CHARS
    chunk_budget = 6000 if expand else LLM_CHUNK_CHARS
    for document in documents:
        if remaining <= 200:
            break
        per_doc = min(chunk_budget, remaining)
        body = _document_context_text(document, per_doc)
        if not body:
            continue
        remaining -= len(body)
        context_blocks.append(
            f"[{document['rank']}] {document['title']} "
            f"(БЗ: {document.get('kb_slug', '')})\n"
            f"URL: {document['permalink']}\n"
            f"{body}"
        )
    context = "\n\n".join(context_blocks)
    query = _last_user_text(messages)
    system_prompt = EXPAND_SYSTEM_PROMPT if expand else GROUNDED_SYSTEM_PROMPT
    grounded = [
        {"role": "system", "content": system_prompt},
        *[
            {"role": item["role"], "content": item["content"]}
            for item in messages
            if item.get("role") != "system"
        ],
    ]
    # Replace last user turn with query + retrieved fragments.
    for index in range(len(grounded) - 1, -1, -1):
        if grounded[index]["role"] == "user":
            grounded[index] = {
                "role": "user",
                "content": (
                    f"Вопрос пользователя:\n{query}\n\n"
                    f"Фрагменты базы знаний:\n{context}\n\n"
                    + (
                        "Разверни полный ответ только по тексту фрагментов: "
                        "все условия, кому подходит, как оформить. "
                        "Допиши ответ до конца, не обрывай предложение. "
                        if expand
                        else "Сформулируй полный ответ только по тексту фрагментов. "
                        "Закончи законченным предложением и законченной мыслью: "
                        "не обрывай фразу, список или абзац на середине. "
                        "Не пиши пустой следующий номер шага. "
                    )
                    + "Числа и сроки бери дословно из тела фрагмента, "
                    "не из имени файла. Отвечай по смыслу вопроса тем, что есть "
                    "во фрагментах. Если фрагменты про другую тему и ответа нет — "
                    "скажи, что в базе знаний нет этой информации, и ничего "
                    "не добавляй от себя. "
                    "Без markdown и без списка источников в тексте."
                ),
            }
            break
    return grounded


def retrieve_assistant_context(
    messages: Sequence[Mapping[str, str]],
    *,
    kb_slugs: Sequence[str] | None = None,
    limit: int = DEFAULT_RAG_LIMIT,
) -> tuple[list[dict[str, Any]], float]:
    """Return documents above the context-inclusion threshold."""
    query = _last_user_text(messages)
    if not query:
        return [], 0.0
    settings = get_model_settings(PROFILE)
    threshold = float(settings.context_inclusion_threshold)
    # Hash stub embeddings yield low absolute cosine scores; keep RAG usable locally.
    if embedding_backend_info()["mode"] == "stub":
        threshold = min(threshold, 0.05)
    result = preview_assistant_query(
        query,
        kb_slugs=kb_slugs,
        limit=limit,
    )
    from qu.assistant_retrieval import contact_fact_signal

    kept: list[dict[str, Any]] = []
    for document in result["documents"]:
        score = float(document["relevance_score"])
        if score >= threshold:
            kept.append(document)
            continue
        signal = contact_fact_signal(
            query,
            str(document.get("title") or ""),
            str(document.get("content") or ""),
        )
        if signal >= 0.2 and score >= 0.15:
            kept.append(document)
    return kept[:limit], threshold


# +18% on the default (non-expand) cap so the last sentence can finish.
_DEFAULT_TOKEN_HEADROOM = 1.18
_EXPAND_TOKEN_FLOOR = 4096
_MIN_RESPONSE_CHARS = 10


def _admin_preset_is_expand() -> bool:
    try:
        return str(get_model_settings(PROFILE).preset) == "long"
    except Exception:
        return False


def _preset_name() -> str:
    """Preset label for the path log. Empty when settings cannot be read."""
    try:
        preset = get_model_settings(PROFILE).preset
    except Exception:
        return ""
    return preset if isinstance(preset, str) else ""


def _effective_expand(requested: bool) -> bool:
    return bool(requested) or _admin_preset_is_expand()


def _response_char_limit(*, expand: bool) -> int | None:
    """Hard cap for the default reply. Expand / «Подробнее» keeps the current long form."""
    if expand:
        return None
    try:
        return max(_MIN_RESPONSE_CHARS, int(get_model_settings(PROFILE).response_chars_max))
    except Exception:
        return None


def _tokens_for_char_limit(char_limit: int) -> int:
    return max(8, int(round(char_limit / 2)) + 8)


def _generation_parameters(*, expand: bool = False) -> dict[str, Any]:
    """Sampling params. Cloud DeepSeek keeps a high ceiling so answers are not cut."""
    try:
        settings = get_model_settings(PROFILE)
        parameters: dict[str, Any] = {
            "temperature": float(settings.temperature),
            "top_p": float(settings.top_p),
            "max_tokens": int(settings.max_tokens),
        }
        char_limit = max(_MIN_RESPONSE_CHARS, int(settings.response_chars_max))
    except Exception:
        parameters = {"max_tokens": 2048}
        char_limit = None

    raw_cap = os.environ.get("ASSISTANT_MAX_TOKENS") or os.environ.get(
        "LLM_MAX_TOKENS"
    )
    if raw_cap:
        try:
            parameters["max_tokens"] = max(32, int(raw_cap))
        except ValueError:
            pass
    elif expand:
        current = int(parameters.get("max_tokens") or 2048)
        try:
            from assistant.local_llm import is_deepseek_assistant

            cloud = is_deepseek_assistant()
        except Exception:
            cloud = False
        if cloud:
            parameters["max_tokens"] = max(current, 4096)
        else:
            parameters["max_tokens"] = max(current, 1024)
    elif char_limit is not None:
        parameters["max_tokens"] = _tokens_for_char_limit(char_limit)
    else:
        current = int(parameters.get("max_tokens") or 2048)
        parameters["max_tokens"] = max(current, 1024)
    base = int(parameters.get("max_tokens") or 2048)
    if expand:
        parameters["max_tokens"] = max(base, _EXPAND_TOKEN_FLOOR)
    elif raw_cap and base < _EXPAND_TOKEN_FLOOR:
        parameters["max_tokens"] = max(32, int(round(base * _DEFAULT_TOKEN_HEADROOM)))
    return parameters


def _iter_plain_sse(text: str) -> Iterator[str]:
    """Stream a fixed reply without calling the LLM."""
    yield (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant"},
                        "finish_reason": None,
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )
    step = 24
    for start in range(0, len(text), step):
        yield (
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": text[start : start + step]},
                            "finish_reason": None,
                        }
                    ],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )
    yield (
        "data: "
        + json.dumps(
            {
                "choices": [
                    {"index": 0, "delta": {}, "finish_reason": "stop"}
                ],
            },
            ensure_ascii=False,
        )
        + "\n\n"
    )
    yield "data: [DONE]\n\n"


def _clip_sse_stream(frames: Iterator[str], limit: int) -> Iterator[str]:
    """Stop the visible answer at ``limit`` characters."""
    used = 0
    stopped = False
    for frame in frames:
        if stopped:
            if frame.strip() == "data: [DONE]":
                yield frame
            continue
        stripped = frame.lstrip()
        if not stripped.startswith("data:"):
            yield frame
            continue
        payload = stripped[5:].strip()
        if payload == "[DONE]":
            yield frame
            continue
        try:
            chunk = json.loads(payload)
        except json.JSONDecodeError:
            yield frame
            continue
        if not isinstance(chunk, dict):
            yield frame
            continue
        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            yield frame
            continue
        first = choices[0]
        if not isinstance(first, dict):
            yield frame
            continue
        delta = first.get("delta")
        if not isinstance(delta, dict):
            yield frame
            continue
        text = delta.get("content")
        if not isinstance(text, str) or not text:
            yield frame
            continue
        remain = limit - used
        if remain <= 0:
            stopped = True
            first["finish_reason"] = "length"
            delta["content"] = ""
            yield (
                "data: "
                + json.dumps(chunk, ensure_ascii=False)
                + "\n\n"
            )
            yield "data: [DONE]\n\n"
            continue
        if len(text) > remain:
            delta["content"] = text[:remain]
            first["finish_reason"] = "length"
            used = limit
            stopped = True
            yield (
                "data: "
                + json.dumps(chunk, ensure_ascii=False)
                + "\n\n"
            )
            yield "data: [DONE]\n\n"
            continue
        used += len(text)
        yield frame
    if not stopped:
        return


def _kb_count(kb_slugs: Sequence[str] | None) -> int:
    if not kb_slugs:
        return 0
    return sum(1 for slug in kb_slugs if str(slug).strip())


def _top_relevance(documents: Sequence[Mapping[str, Any]]) -> int | float | None:
    if not documents:
        return None
    value = documents[0].get("relevance_percent")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _message_chars(messages: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for item in messages:
        content = item.get("content")
        if isinstance(content, str):
            total += len(content)
    return total


def _included_rag_chars(
    documents: Sequence[Mapping[str, Any]],
    *,
    expand: bool,
) -> int:
    """Length of fragment bodies that ``_inject_rag_context`` puts in the prompt."""
    remaining = 16000 if expand else LLM_RAG_TOTAL_CHARS
    chunk_budget = 6000 if expand else LLM_CHUNK_CHARS
    total = 0
    for document in documents:
        if remaining <= 200:
            break
        per_doc = min(chunk_budget, remaining)
        body = _document_context_text(document, per_doc)
        if not body:
            continue
        remaining -= len(body)
        total += len(body)
    return total


def _append_capped(parts: list[str], text: str, limit: int = 4000) -> None:
    if not text:
        return
    used = sum(len(part) for part in parts)
    if used >= limit:
        return
    parts.append(text[: limit - used])


def _sse_delta_text(frame: str) -> str:
    stripped = frame.lstrip()
    if not stripped.startswith("data:"):
        return ""
    payload = stripped[5:].strip()
    if not payload or payload == "[DONE]":
        return ""
    try:
        chunk = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if not isinstance(chunk, dict):
        return ""
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    delta = choices[0].get("delta")
    if not isinstance(delta, dict):
        return ""
    text = delta.get("content")
    return text if isinstance(text, str) else ""


def _sse_frame_has_content(frame: str) -> bool:
    return bool(_sse_delta_text(frame))


def _timed_outbound(
    frames: Iterator[str],
    marks: dict[str, float | None],
    sink: list[str] | None = None,
) -> Iterator[str]:
    """Yield the same frames and record time-to-first text plus stream duration."""
    started = time.perf_counter()
    try:
        for frame in frames:
            if sink is not None:
                _append_capped(sink, _sse_delta_text(frame))
            if marks["ttft_ms"] is None and _sse_frame_has_content(frame):
                marks["ttft_ms"] = elapsed_ms(started)
            yield frame
    finally:
        marks["llm_ms"] = elapsed_ms(started)


def iter_chat_sse(
    messages: Sequence[Mapping[str, str]],
    *,
    kb_slugs: Sequence[str] | None = None,
    gateway: ModelGateway | None = None,
    request_id: str | None = None,
    expand: bool = False,
    skill_instruction: str = "",
    actor: str = "",
    message_id: str = "",
    session_id: str = "",
    department: str = "",
) -> Iterator[str]:
    """Yield OpenAI-compatible SSE frames from ``assistant_bank`` with RAG."""
    started = time.perf_counter()
    requested_expand = bool(expand)
    outcome: str | None = None
    filter_ms: float | None = None
    retrieval_ms: float | None = None
    prompt_ms: float | None = None
    prompt_chars: int | None = None
    rag_chars: int | None = None
    max_tokens: int | None = None
    doc_count = 0
    top_relevance: int | float | None = None
    attachment_mode = False
    source_title = ""
    answer_parts: list[str] = []
    skill_used = bool(skill_instruction)
    token_marks: dict[str, float | None] = {"ttft_ms": None, "llm_ms": None}
    try:
        filter_started = time.perf_counter()
        try:
            content_hit = match_content_filter(_filter_query(messages))
        except Exception:
            logger.exception("content_filter_match_failed")
            content_hit = None
        filter_ms = elapsed_ms(filter_started)
        if content_hit is not None:
            outcome = "content_filter"
            try:
                audit_content_filter_block(username=actor, code=content_hit.code)
            except Exception:
                logger.exception("content_filter_audit_failed")
            yield from _iter_plain_sse(content_hit.refusal_text)
            _append_capped(answer_parts, content_hit.refusal_text)
            return

        expand = _effective_expand(expand)
        char_limit = _response_char_limit(expand=expand)
        active = gateway or ModelGateway.from_registry()
        parameters = _generation_parameters(expand=expand)
        raw_max_tokens = parameters.get("max_tokens")
        if isinstance(raw_max_tokens, int) and not isinstance(raw_max_tokens, bool):
            max_tokens = raw_max_tokens

        if request_id:
            yield f": request_id {request_id}\n\n"

        # Immediate SSE frame so proxies/UI know the stream is alive while we embed.
        yield (
            "data: "
            + json.dumps(
                {
                    "status": "retrieving",
                    "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        documents: list[dict[str, Any]] = []
        attachment_mode = has_attachment_marker(messages)
        if not attachment_mode:
            retrieval_started = time.perf_counter()
            try:
                documents, _threshold = retrieve_assistant_context(
                    messages,
                    kb_slugs=kb_slugs,
                )
            except Exception:
                documents = []
            retrieval_ms = elapsed_ms(retrieval_started)

        doc_count = len(documents)
        top_relevance = _top_relevance(documents)
        if documents:
            source_title = str(documents[0].get("title") or "")
        sources = [_citation(document) for document in documents]
        yield (
            "data: "
            + json.dumps(
                {
                    "status": "generating",
                    "sources": sources,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": None}],
                },
                ensure_ascii=False,
            )
            + "\n\n"
        )

        if not documents and not attachment_mode and not skill_instruction:
            outcome = "no_kb"
            _append_capped(answer_parts, NO_KB_ANSWER)
            yield from _iter_plain_sse(NO_KB_ANSWER)
            return

        prompt_started = time.perf_counter()
        outbound = (
            _inject_rag_context(messages, documents, expand=expand)
            if documents
            else list(messages)
        )
        if not documents:
            if attachment_mode:
                empty_system = (
                    "Ты внутренний ИИ-ассистент банка. Пользователь загрузил "
                    "документ. "
                    + (
                        "Сделай полное резюме по фрагментам вложения. "
                        if wants_summary(_last_user_text(messages))
                        else "Ответь на вопрос только по фрагментам вложения. "
                    )
                    + "Заканчивай законченным предложением и законченной мыслью. "
                    + _ANSWER_STYLE
                )
            else:
                empty_system = (
                    (EXPAND_SYSTEM_PROMPT if expand else DEFAULT_SYSTEM_PROMPT)
                    + " В выбранных базах знаний релевантных фрагментов "
                    "не найдено — сообщи об этом пользователю."
                )
            outbound = [
                {
                    "role": "system",
                    "content": empty_system,
                },
                *[
                    {"role": item["role"], "content": item["content"]}
                    for item in outbound
                    if item.get("role") != "system"
                ],
            ]

        if skill_instruction:
            outbound = apply_skill_layer(
                [dict(item) for item in outbound],
                skill_instruction,
            )

        if char_limit is not None:
            length_hint = f" Ответ строго не длиннее {char_limit} символов."
            outbound = [
                {
                    **item,
                    "content": f"{item['content']}{length_hint}",
                }
                if item.get("role") == "system"
                else item
                for item in outbound
            ]

        outbound = apply_content_filter_instruction(outbound)
        prompt_ms = elapsed_ms(prompt_started)
        prompt_chars = _message_chars(outbound)
        rag_chars = (
            _included_rag_chars(documents, expand=expand) if documents else 0
        )

        try:
            stream = active.stream(PROFILE, outbound, **parameters)
            if char_limit is not None:
                stream = _clip_sse_stream(stream, char_limit)
            yield from _timed_outbound(stream, token_marks, answer_parts)
        except ModelGatewayConfigurationError as exc:
            outcome = "llm_error"
            raise AssistantChatError(str(exc)) from exc
        except Exception as exc:
            # Surface gateway/network errors into the SSE so the UI stops spinning.
            outcome = "llm_error"
            _append_capped(answer_parts, "Не удалось получить ответ от модели.")
            err = str(exc) or exc.__class__.__name__
            yield (
                "data: "
                + json.dumps(
                    {
                        "error": "llm_error",
                        "details": err,
                        "choices": [
                            {
                                "index": 0,
                                "delta": {
                                    "content": (
                                        "Не удалось получить ответ от модели: "
                                        f"{err}"
                                    )
                                },
                                "finish_reason": "stop",
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            yield "data: [DONE]\n\n"
        else:
            outcome = "streamed"
    except GeneratorExit:
        outcome = "client_closed"
        raise
    except AssistantChatError:
        outcome = "llm_error"
        raise
    finally:
        total_ms = elapsed_ms(started)
        ttft_ms = token_marks["ttft_ms"]
        log_path(
            {
                "path": "chat",
                "request_id": request_id or "-",
                "outcome": outcome,
                "expand": requested_expand,
                "preset": _preset_name(),
                "profile": PROFILE,
                "kb_count": _kb_count(kb_slugs),
                "doc_count": doc_count,
                "history_count": len(messages),
                "top_relevance": top_relevance,
                "rag_chars": rag_chars,
                "prompt_chars": prompt_chars,
                "max_tokens": max_tokens,
                "filter_ms": filter_ms,
                "retrieval_ms": retrieval_ms,
                "prompt_ms": prompt_ms,
                "ttft_ms": ttft_ms,
                "llm_ms": token_marks["llm_ms"],
                "total_ms": total_ms,
                "preview_text_ms": ttft_ms,
                "first_text_ms": ttft_ms,
            }
        )
        from assistant.monitoring_record import record_chat_event

        try:
            record_chat_event(
                request_id=request_id or "",
                message_id=message_id,
                session_id=session_id,
                username=actor,
                department=department,
                question_text=_filter_query(messages),
                answer_text="".join(answer_parts),
                outcome=outcome,
                total_ms=total_ms,
                ttft_ms=ttft_ms,
                llm_ms=token_marks["llm_ms"],
                top_relevance=(
                    top_relevance
                    if isinstance(top_relevance, (int, float))
                    and not isinstance(top_relevance, bool)
                    else None
                ),
                doc_count=doc_count,
                kb_slugs=[str(slug) for slug in (kb_slugs or [])],
                source_title=source_title,
                attachment_mode=attachment_mode,
                skill_used=skill_used,
            )
        except Exception as exc:
            logger.warning(
                "metric_write_failed request_id=%s error_type=%s",
                request_id or "-",
                type(exc).__name__,
            )
