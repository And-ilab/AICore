"""Sufler CC pipeline: text → QU → RAG → ModelGateway(sufler_cc) → citations.

Implements FR-CC-03 (LLM hints from ``cc_production``) and FR-CC-14
(operator-visible source title + permalink). Stage latency is logged for
FR-CC / KPI budgets.
"""

from __future__ import annotations

import logging
import os
import re
import time
import uuid
from typing import Any, Mapping, Sequence

from core.model_gateway import ModelGateway
from core.text_language import safe_ru_en_text
from hub.model_registry_store import get_model_settings
from hub.models import SuflerPolicy
from hub.sufler_policy import get_sufler_policy
from orchestrator.scenario_engine import (
    NO_HINT_REASON,
    ScenarioProgress,
    SuggestedScenario,
    classify_turn,
    is_social_turn,
    clear_scenario_session,
    enter_scenario,
    pause_scenario_session,
    resolve_scenario_turn,
    resume_scenario,
)
from qu.service import (
    _tokens,
    complete_sentences,
    extractive_answer,
    focused_snippet,
    ignored_suz_fixtures_exist,
    is_suz_transfer_commission_doc,
    preview_query,
)

logger = logging.getLogger(__name__)

PROFILE = "sufler_cc"
KB_ID = "cc_production"
DEFAULT_HINT_LIMIT = 1
MAX_HINT_LIMIT = 5
# Fallback if policy row is missing: never show hints below 20% relevance.
OPERATOR_MIN_RELEVANCE = 0.20
# Prefer a second hint when it is reasonably close to the best match.
SECOND_HINT_RELATIVE_FLOOR = 0.55

SCENARIO_PHRASE_PROMPT = (
    "Ты суфлёр оператора контакт-центра Беларусбанка. "
    "Напиши ОДНУ готовую реплику оператора от первого лица, которую можно "
    "прочитать клиенту дословно. Это живой диалог, а не пересказ вопроса. "
    "Запрещено начинать с «Вы спрашиваете», «Как я понимаю», «Вы обратились», "
    "«Вы хотите уточнить». Не повторяй формулировку клиента. "
    "Не задавай вопрос, на который клиент уже ответил в этой реплике "
    "(возраст, карта, продукт). Если ответ уже есть — сразу следующий шаг "
    "или суть узла, без тавтологии. "
    "Если нужно уточнение — в конце задай ОДИН естественный вопрос оператора "
    "клиенту, например: «Вы законный представитель или нет?». "
    "Не зачитывай варианты ответа клиента дословно и не говори от его лица "
    "(запрещены фразы вроде «Я дедушка» / «Я мама»). "
    "Опирайся на прошлую реплику клиента: не предлагай то, "
    "на что он уже ответил. Не больше одного вопроса за реплику. "
    "Если вариантов нет — это финальный шаг, не задавай новых вопросов. "
    "Запрещены слова СУЗ, «статья», «база знаний», «перед ответом» и любые "
    "пометки оператору: клиент это услышит. "
    "Если клиент уже просит карту — скажи, что откроем счёт и оформим к нему "
    "карту, и спроси только следующий шаг из вариантов. "
    "Не спрашивай «с карточкой или без». "
    "Не выдумывай ставки, сроки, комиссии и условия, которых нет в скрипте. "
    "Только текст реплики, без markdown, без заголовков и без слова «ОТВЕТ»."
)

SCENARIO_RETURN_PHRASE_PROMPT = (
    "Ты суфлёр оператора контакт-центра Беларусбанка. "
    "Клиент ушёл с темы или мог забыть, зачем обратился. "
    "Оператор возвращается к незакрытому шагу сценария. "
    "Напиши ОДНУ готовую реплику оператора от первого лица, "
    "чтобы мягко продолжить старый диалог и добить то, что хотел клиент. "
    "Запрещено начинать с «Вы спрашиваете», «Как я понимаю», «Вы обратились». "
    "Если есть варианты ответа клиента из сценария — в конце реплики "
    "ОБЯЗАТЕЛЬНО один наводящий вопрос по этим вариантам. "
    "Не больше одного вопроса за реплику. "
    "Не выдумывай ставки, сроки, комиссии и условия, которых нет в скрипте. "
    "Запрещены слова СУЗ, «статья», «база знаний» и любые пометки оператору. "
    "Только текст реплики, без markdown, без заголовков и без слова «ОТВЕТ»."
)

SYSTEM_PROMPT = (
    "Ты суфлёр оператора контакт-центра Беларусбанка. "
    "Пиши ТОЛЬКО на грамотном русском или английском языке. "
    "По умолчанию отвечай по-русски; английский используй только когда он "
    "нужен клиенту. Запрещены китайские иероглифы и любые другие алфавиты, "
    "транслит, смесь языков, опечатки и грамматические ошибки. "
    "Отвечай СТРОГО на основе переданных фрагментов базы знаний. "
    "Не выдумывай факты, цифры, тарифы, сроки и условия, которых нет во фрагментах.\n"
    "Если во фрагментах есть точная цифра или срок — обязательно включи её в ОТВЕТ целиком.\n"
    "Учитывай весь диалог: уточнения клиента (тип карты, продукт и т.п.) "
    "должны влиять на формулировку ответа.\n"
    "Формат ответа СТРОГО (без markdown, без звёздочек *, без жирного):\n"
    "ОТВЕТ:\n"
    "<готовая реплика оператора от первого лица, которую можно прочитать клиенту дословно; "
    "2–5 законченных предложений, без обрыва на полуслове. ЗАПРЕЩЕНО писать вопросы, в том числе риторические. "
    "Не копируй вопросы из статьи. Без «Уважаемый клиент». "
    "Без «Вы спрашиваете». Без слов СУЗ, «статья базы», «перед ответом»>\n"
    "ПОДРОБНЕЕ:\n"
    "<та же осознанная реплика оператора, но длиннее: 5–8 предложений. "
    "Разверни условия, кому подходит, как оформить и исключения — только из фрагментов. "
    "Не копируй сырой текст статьи, ссылки, даты сбора, имена файлов и заголовки страниц. "
    "Не выдумывай цифры. Без вопросов>\n"
    "СОВЕТ:\n"
    "<одна короткая ремарка оператору только если нужна; иначе оставь пустым>\n"
    "Не пиши заголовки вроде «Подсказка оператору» или «Ответ клиенту». "
    "Не пересказывай историю обращений и не цитируй реплики диалога дословно."
)


def _runtime_model_or_empty(gateway: ModelGateway) -> str:
    try:
        return gateway.get_runtime_model(PROFILE)
    except Exception:  # noqa: BLE001 — model name is metadata only
        logger.exception("sufler_runtime_model_failed")
        return ""


class SuflerOrchestratorError(ValueError):
    """Raised when suggest input or pipeline configuration is invalid."""


def _policy_settings() -> SuflerPolicy:
    try:
        return get_sufler_policy()
    except Exception:  # noqa: BLE001 — suggest must not fail if admin table is empty
        logger.exception("sufler_policy_load_failed")
        return SuflerPolicy(
            telephony_min_relevance_percent=20,
            clarify_min_relevance_percent=15,
            max_hints=DEFAULT_HINT_LIMIT,
            default_mode=SuflerPolicy.MODE_CONSULTATION,
        )


def _normalize_channel(channel: str) -> str:
    key = (channel or "").strip().lower()
    if key in {"online_chat", "chat", "widget"}:
        return "online_chat"
    return "telephony"


def _normalize_mode(mode: str, *, default: str) -> str:
    key = (mode or "").strip().lower()
    if key in {SuflerPolicy.MODE_SERVICE, "usluga"}:
        return SuflerPolicy.MODE_SERVICE
    if key in {SuflerPolicy.MODE_CONSULTATION, "consult"}:
        return SuflerPolicy.MODE_CONSULTATION
    return default or SuflerPolicy.MODE_CONSULTATION


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _citation(document: Mapping[str, Any]) -> dict[str, Any]:
    title = _safe_ru_en_text(str(document.get("title") or ""))
    return {
        "article_id": document["article_id"],
        "chunk_index": document["chunk_index"],
        "title": title or "Документ базы знаний",
        "permalink": document["permalink"],
    }


def _safe_ru_en_text(text: str) -> str:
    return safe_ru_en_text(text)


def _document_is_ru_en(document: Mapping[str, Any]) -> bool:
    title = str(document.get("title") or "")
    body = str(document.get("content") or document.get("snippet") or "")
    return bool(_safe_ru_en_text(title)) and bool(_safe_ru_en_text(body))


_INTERNAL_OPERATOR_MARK = re.compile(
    r"(?i)(?:\bсуз\b|стать[еёию]\s+(?:базы|знаний|суз)|перед ответом|"
    r"сверьте\s+(?:актуальн|формул)|назовите комиссию по|"
    r"уточните (?:комиссию|лимит|ставку).{0,60}стать)"
)
_TAUTOLOGY_OPENER = re.compile(
    r"(?is)^\s*(?:"
    r"вы\s+спрашиваете[^.!?\n]*[.!?…]?\s*"
    r"|как\s+я\s+понимаю[^.!?\n]*[.!?…]?\s*"
    r"|вы\s+обратились[^.!?\n]*[.!?…]?\s*"
    r"|вы\s+(?:хотите|хотели)\s+(?:уточнить|узнать)[^.!?\n]*[.!?…]?\s*"
    r"|понял(?:а|и)?[,]?\s+вы\s+[^.!?\n]*[.!?…]?\s*"
    r")+"
)


def _client_age_under_14(query: str) -> bool:
    folded = (query or "").casefold()
    if re.search(r"\b(1[4-9]|[2-9]\d)\s*лет", folded):
        return False
    if re.search(r"\b(1[0-3]|[1-9])\s*лет", folded):
        return True
    return any(
        word in folded
        for word in (
            "шесть",
            "семь",
            "восемь",
            "девять",
            "десять",
            "одиннадцать",
            "двенадцать",
            "тринадцать",
        )
    )


def _client_asked_for_card(query: str) -> bool:
    folded = (query or "").casefold()
    if "без карт" in folded or "без карточ" in folded:
        return False
    return "карт" in folded


def _is_internal_operator_sentence(sentence: str) -> bool:
    return bool(_INTERNAL_OPERATOR_MARK.search(sentence or ""))


def _drop_already_answered(sentences: list[str], query: str) -> list[str]:
    kept: list[str] = []
    age_known = _client_age_under_14(query)
    wants_card = _client_asked_for_card(query)
    for sentence in sentences:
        folded = sentence.casefold()
        if age_known and re.search(r"14\s*лет|четырнадцат", folded):
            continue
        if wants_card and re.search(
            r"с карт\w* или без|без карт\w* или с",
            folded,
        ):
            continue
        kept.append(sentence)
    return kept


def _sanitize_spoken_phrase(text: str, query: str = "") -> str:
    """Keep only words the operator can read aloud to the client."""
    cleaned = _strip_markup(text)
    if not cleaned:
        return ""
    cleaned = _TAUTOLOGY_OPENER.sub("", cleaned).strip()
    parts = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", cleaned) if part.strip()]
    without_internal = [
        part for part in parts if not _is_internal_operator_sentence(part)
    ]
    kept = _drop_already_answered(without_internal, query)
    return " ".join(kept).strip()


def _drop_invented_questions(text: str) -> str:
    parts = [part.strip() for part in re.split(r"(?<=[.!?…])\s+", text) if part.strip()]
    kept = [part for part in parts if not part.endswith("?")]
    return " ".join(kept).strip()


def _strip_markup(text: str) -> str:
    cleaned = _safe_ru_en_text(text)
    if not cleaned:
        return ""
    cleaned = cleaned.replace("**", "").replace("__", "")
    cleaned = re.sub(r"[*_`]+", "", cleaned)
    cleaned = re.sub(
        r"^\s*(подсказка оператору|ответ клиенту|совет оператору)\s*:?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


_SECTION_BREAK = r"(?:\n\s*(?:ответ|подробнее|совет)\s*:|$)"


def _parse_llm_hint(raw: str) -> tuple[str, str, str]:
    """Return (client_answer, optional_operator_tip, longer_detail)."""
    text = _strip_markup(raw)
    if not text:
        return "", "", ""
    answer = text
    tip = ""
    detail = ""
    answer_match = re.search(
        rf"ответ\s*:\s*(.*?){_SECTION_BREAK}",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    detail_match = re.search(
        rf"подробнее\s*:\s*(.*?){_SECTION_BREAK}",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    tip_match = re.search(
        r"совет\s*:\s*(.*)$",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if answer_match:
        answer = answer_match.group(1).strip()
    if detail_match:
        detail = detail_match.group(1).strip()
    if tip_match:
        tip = tip_match.group(1).strip()
        tip_lower = tip.casefold()
        if tip_lower in {"", "-", "нет", "не нужен", "не требуется", "пусто"}:
            tip = ""
    if not answer_match:
        answer = re.sub(
            r"(?is)^\s*(?:подробнее|совет)\s*:.*$",
            "",
            answer,
        ).strip()
    return _strip_markup(answer), _strip_markup(tip), _strip_markup(detail)


def _clean_answer_text(text: str) -> str:
    """Keep only declarative sentences suitable to paste to the client."""
    cleaned = _strip_markup(text)
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?…])\s+", cleaned)
    kept: list[str] = []
    for sentence in sentences:
        piece = sentence.strip()
        if not piece:
            continue
        # Drop interrogatives and seed "title. Question?" prefixes.
        if "?" in piece:
            continue
        if re.match(
            r"^(какой|какая|какие|как|где|когда|зачем|почему|что|сколько)\b",
            piece,
            flags=re.IGNORECASE,
        ):
            continue
        kept.append(piece)
    result = " ".join(kept).strip()
    return _sanitize_spoken_phrase(result or cleaned)


def _snippet_as_answer(document: Mapping[str, Any], query: str = "") -> str:
    raw = _strip_source_noise(
        str(document.get("content") or document.get("snippet") or "")
    )
    if not _safe_ru_en_text(raw):
        return ""
    extracted = extractive_answer(raw, query or str(document.get("title") or ""))
    return _clean_answer_text(extracted)


# qu.service._tokens already stems to 4 letters; keep these generic.
_ATTRIBUTION_STEMS = (
    "офор",
    "заяв",
    "доку",
    "услу",
    "клие",
    "отде",
)


def _attribution_tokens(text: str) -> set[str]:
    return {
        token
        for token in _query_specific_tokens(text)
        if not any(token.startswith(stem) for stem in _ATTRIBUTION_STEMS)
    }


def _llm_misses_source(answer: str, document: Mapping[str, Any]) -> bool:
    return not _answer_uses_document(answer, document)


def _answer_uses_document(answer: str, document: Mapping[str, Any]) -> bool:
    """True only when the hint is actually taken from this KB file."""
    source = _attribution_tokens(
        f"{document.get('title') or ''}\n"
        f"{document.get('content') or document.get('snippet') or ''}"
    )
    answer_tokens = _attribution_tokens(answer)
    if not source or not answer_tokens:
        return False
    overlap = source & answer_tokens
    if len(overlap) >= 2:
        return True
    return any(len(token) >= 8 for token in overlap)


_GENERIC_QUERY_TOKENS = {
    "банк",
    "бела",
    "беларус",
    "беларусбанк",
    "вопрос",
    "клиент",
    "надо",
    "нужн",
    "може",
    "можн",
    "опера",
    "пожал",
    "подскаж",
    "хочу",
    "хоте",
}


def _query_specific_tokens(query: str) -> set[str]:
    return {
        token
        for token in _tokens(query)
        if len(token) >= 4 and token not in _GENERIC_QUERY_TOKENS
    }


def _document_supports_query(document: Mapping[str, Any], query: str) -> bool:
    """Require lexical evidence before attributing an answer to a KB file."""
    query_tokens = _attribution_tokens(query)
    if not query_tokens:
        return False
    source_tokens = _attribution_tokens(
        f"{document.get('title') or ''}\n"
        f"{document.get('content') or document.get('snippet') or ''}"
    )
    return bool(query_tokens & source_tokens)


def _retrieval_query(text: str, dialog_context: str = "") -> str:
    """Build RAG query from latest client line + recent dialog turns."""
    latest = (text or "").strip()
    context = (dialog_context or "").strip()
    if not context:
        return latest
    # Keep the latest utterance first for lexical overlap, then prior turns.
    combined = f"{latest}\n{context}"
    return combined[:1200].strip()


_CALL_TOPIC_STEMS = (
    "авто",
    "автокредит",
    "автомобил",
    "адаптац",
    "аттестац",
    "больничн",
    "вклад",
    "виз",
    "выписк",
    "график",
    "деньг",
    "декрет",
    "договор",
    "зарплат",
    "залог",
    "ипотек",
    "испытательн",
    "карт",
    "командир",
    "кредит",
    "крипт",
    "льгот",
    "материн",
    "машин",
    "обучен",
    "оплат",
    "отпуск",
    "перевод",
    "перевест",
    "пин",
    "пособи",
    "посольств",
    "преми",
    "процент",
    "рефинанс",
    "справк",
    "ставк",
    "счет",
)
_QUESTION_WORDS = {
    "зачем",
    "где",
    "как",
    "какая",
    "какие",
    "какое",
    "какой",
    "когда",
    "кто",
    "куда",
    "можно",
    "почему",
    "сколько",
    "что",
    "чем",
}
_QUESTION_FILLER = {
    "будет",
    "было",
    "были",
    "вас",
    "вообще",
    "вот",
    "еще",
    "ещё",
    "есть",
    "меня",
    "нам",
    "нет",
    "очень",
    "просто",
    "сейчас",
    "там",
    "тебя",
    "только",
    "тут",
    "уже",
    "эта",
    "эти",
    "это",
    "этого",
    "этой",
    "этом",
    "этот",
}
_JUNK_TITLE_RE = re.compile(
    r"(?iu)(no\s*send|тестов\w*\s+запис|агент\s+\d|\d{2,4}\s+агент)"
)


def _folded_spaces(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _call_tokens(text: str) -> list[str]:
    folded = text.casefold().replace("ё", "е")
    return re.findall(r"[0-9a-zа-я]+", folded)


def telephony_turn_needs_hint(text: str) -> bool:
    """A live replica needs a card only when it is about a bank topic or a real question."""
    tokens = _call_tokens(text or "")
    if not tokens:
        return False
    if any(token.startswith(stem) for token in tokens for stem in _CALL_TOPIC_STEMS):
        return True
    if not any(token in _QUESTION_WORDS for token in tokens):
        return False
    content = [
        token
        for token in tokens
        if len(token) >= 5 and token not in _QUESTION_WORDS and token not in _QUESTION_FILLER
    ]
    return bool(content)


def _is_junk_kb_document(document: Mapping[str, Any]) -> bool:
    """Drop test articles and cards whose text is only the title."""
    title = _folded_spaces(document.get("title"))
    if title and _JUNK_TITLE_RE.search(title):
        return True
    body = _folded_spaces(document.get("content") or document.get("snippet"))
    return bool(title and body and body == title)


def _select_documents(
    documents: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    context_threshold: float,
    allow_weak: bool = False,
    query: str = "",
    min_relevance: float = OPERATOR_MIN_RELEVANCE,
) -> list[Mapping[str, Any]]:
    """Return 1…limit docs above the operator relevance floor from policy."""
    floor_score = max(float(min_relevance), 0.0)
    pool = [
        document
        for document in documents
        if not is_suz_transfer_commission_doc(document)
        and _document_is_ru_en(document)
        and not _is_junk_kb_document(document)
    ]
    if not pool:
        return []
    floor = max(float(context_threshold), floor_score)
    ranked = [
        document
        for document in pool
        if float(document["relevance_score"]) >= floor_score
        and float(document["relevance_score"]) >= floor
    ]
    # Soft floor: still allow docs at/above the policy threshold even if below RAG.
    if not ranked:
        ranked = [
            document
            for document in pool
            if float(document["relevance_score"]) >= floor_score
        ]
    if not ranked and allow_weak:
        ranked = sorted(
            pool,
            key=lambda document: -float(document["relevance_score"]),
        )[:limit]
    if not ranked:
        return []
    ranked = _merge_article_chunks(ranked, query=query)
    selected: list[Mapping[str, Any]] = [ranked[0]]
    if limit >= 2:
        best = float(ranked[0]["relevance_score"])
        second_floor = max(
            0.0 if allow_weak else floor_score + 0.01,
            best * SECOND_HINT_RELATIVE_FLOOR,
        )
        selected_ids = {selected[0]["article_id"]}
        for document in ranked[1:]:
            if document["article_id"] in selected_ids:
                continue
            if float(document["relevance_score"]) >= second_floor:
                selected.append(document)
                selected_ids.add(document["article_id"])
            if len(selected) >= limit:
                break
    return selected[:limit]


def _sufler_llm_configured() -> bool:
    if (os.getenv("SUFLER_LLM_BASE_URL") or "").strip():
        return True
    openai = (os.getenv("OPENAI_BASE_URL") or "").strip()
    return bool(openai)


def _allow_ungrounded() -> bool:
    flag = os.getenv("SUFLER_ALLOW_UNGROUNDED", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return True
    if flag in {"0", "false", "no"}:
        return False
    return _sufler_llm_configured()


def _document_body(document: Mapping[str, Any]) -> str:
    raw = str(document.get("content") or document.get("snippet") or "")
    if not _safe_ru_en_text(raw):
        return ""
    return complete_sentences(_strip_markup(raw), max_chars=6000)


_SOURCE_NOISE_LINE = re.compile(
    r"(?im)^\s*(?:дата\s+сбора|источник|url|permalink|файл)\s*:.*$"
)
_SOURCE_URL = re.compile(r"https?://\S+", re.IGNORECASE)
_SOURCE_FILE = re.compile(r"\b[\w.-]+\.(?:txt|md|html|pdf)\b", re.IGNORECASE)


def _strip_source_noise(text: str) -> str:
    cleaned = _SOURCE_NOISE_LINE.sub("", text or "")
    cleaned = _SOURCE_URL.sub("", cleaned)
    cleaned = _SOURCE_FILE.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _looks_like_source_dump(text: str) -> bool:
    lowered = (text or "").casefold()
    if not lowered.strip():
        return True
    if "дата сбора" in lowered or "belarusbank.by" in lowered:
        return True
    if "http://" in lowered or "https://" in lowered:
        return True
    if _SOURCE_FILE.search(lowered):
        return True
    return False


def _spoken_detail_from_document(
    document: Mapping[str, Any] | None,
    spoken: str,
    query: str = "",
) -> str:
    """Operator-style expansion from the article, never the raw scrape dump."""
    spoken = (spoken or "").strip()
    if document is None:
        return spoken
    raw = _strip_source_noise(
        str(document.get("content") or document.get("snippet") or "")
    )
    if not _safe_ru_en_text(raw):
        return spoken
    extracted = extractive_answer(
        raw,
        query or str(document.get("title") or ""),
        max_chars=1600,
    )
    cleaned = _clean_answer_text(extracted)
    cleaned = complete_sentences(cleaned, max_chars=1600)
    if not cleaned or _looks_like_source_dump(cleaned):
        return spoken
    return cleaned


def _finalize_detail_text(*candidates: str, spoken: str) -> str:
    spoken = (spoken or "").strip()
    for item in candidates:
        cleaned = _clean_answer_text(_strip_source_noise(item or ""))
        if not cleaned or _looks_like_source_dump(cleaned):
            continue
        return complete_sentences(cleaned, max_chars=1600)
    return spoken


def _expand_kb_detail_llm(
    *,
    query: str,
    spoken: str,
    document: Mapping[str, Any] | None,
    gateway: ModelGateway,
    settings: Any,
) -> str:
    if (os.environ.get("MODEL_GATEWAY_MODE") or "").strip().lower() == "stub":
        return ""
    if not spoken.strip() or document is None:
        return ""
    body = _strip_source_noise(_document_body(document))[:3500]
    if not body:
        return ""
    user_content = (
        f"Реплика клиента:\n{query}\n\n"
        f"Короткий ответ оператора:\n{spoken}\n\n"
        f"Фрагмент базы знаний «{document.get('title') or ''}»:\n{body}\n\n"
        "Напиши более подробную готовую реплику оператора от первого лица "
        "по тем же фактам. 5–8 законченных предложений. "
        "Разверни условия, кому подходит и как оформить. "
        "Не копируй сырой текст, ссылки, даты сбора и имена файлов. "
        "Не выдумывай цифры и тарифы. Без вопросов. Только текст реплики."
    )
    try:
        response = gateway.chat(
            PROFILE,
            [
                {
                    "role": "system",
                    "content": (
                        "Ты суфлёр оператора контакт-центра Беларусбанка. "
                        "Пиши только грамотным русским. "
                        "Не выдумывай факты, которых нет во фрагменте."
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=float(settings.temperature),
            top_p=float(settings.top_p),
            max_tokens=min(max(int(settings.max_tokens), 280), 450),
        )
        expanded = _clean_answer_text(_extract_llm_text(response))
        if expanded and not _looks_like_source_dump(expanded):
            return complete_sentences(expanded, max_chars=1600)
    except Exception:  # noqa: BLE001 — keep the short spoken hint
        logger.exception("sufler_kb_detail_expand_failed")
    return ""


def _kb_hint_payload(
    *,
    rank: int,
    text: str,
    operator_tip: str,
    document: Mapping[str, Any] | None,
    relevance_score: float,
    relevance_percent: int,
    citations: list[dict[str, Any]],
    detail_text: str = "",
    query: str = "",
) -> dict[str, Any]:
    spoken = (text or "").strip()
    detail = _finalize_detail_text(detail_text, spoken="")
    if not detail or len(detail) < len(spoken) + 40:
        detail = _spoken_detail_from_document(document, spoken, query) or spoken
    return {
        "rank": rank,
        "text": spoken,
        "detail_text": detail,
        "operator_tip": operator_tip,
        "source_type": "knowledge_base",
        "relevance_score": relevance_score,
        "relevance_percent": relevance_percent,
        "citations": citations,
    }


def _merge_article_chunks(
    documents: Sequence[Mapping[str, Any]],
    *,
    query: str = "",
) -> list[dict[str, Any]]:
    """Join chunks of one file so the LLM sees the answering clause, not only the header."""
    merged: dict[int, dict[str, Any]] = {}
    order: list[int] = []
    for document in documents:
        article_id = int(document["article_id"])
        body = str(document.get("content") or document.get("snippet") or "").strip()
        if article_id not in merged:
            order.append(article_id)
            item = dict(document)
            item["content"] = body
            merged[article_id] = item
            continue
        current = merged[article_id]
        if body and body not in current["content"]:
            current["content"] = f"{current['content']}\n{body}".strip()
        current["relevance_score"] = max(
            float(current["relevance_score"]),
            float(document["relevance_score"]),
        )
        current["relevance_percent"] = round(float(current["relevance_score"]) * 100)
        if int(document.get("chunk_index") or 0) < int(current.get("chunk_index") or 0):
            current["chunk_index"] = document["chunk_index"]
    result: list[dict[str, Any]] = []
    for article_id in order:
        item = merged[article_id]
        item["snippet"] = focused_snippet(item["content"], query, 1200)
        result.append(item)
    return result


def _build_messages(
    query: str,
    documents: Sequence[Mapping[str, Any]],
    *,
    client_history: str = "",
    dialog_context: str = "",
    kb_label: str = KB_ID,
    brief: bool = False,
) -> list[dict[str, str]]:
    context_blocks = []
    source_documents = documents[:2] if brief else documents
    for document in source_documents:
        if brief:
            # The answering clause is often far below the regulation header.
            raw = str(document.get("content") or document.get("snippet") or "")
            body = complete_sentences(
                _strip_markup(focused_snippet(raw, query, 1600)),
                max_chars=1100,
            )
        else:
            body = _document_body(document)
        context_blocks.append(
            f"[{document['rank']}] {document['title']}\n"
            f"URL: {document['permalink']}\n"
            f"{body}"
        )
    context = "\n\n".join(context_blocks)
    history_block = ""
    cleaned_history = client_history.strip() if isinstance(client_history, str) else ""
    if cleaned_history:
        history_block = (
            "Служебный контекст прошлых обращений "
            "(не включать в текст ответа клиенту):\n"
            f"{cleaned_history[:800]}\n\n"
        )
    dialog_block = ""
    cleaned_dialog = dialog_context.strip() if isinstance(dialog_context, str) else ""
    if cleaned_dialog:
        dialog_block = (
            "Текущая переписка (учитывай уточнения клиента):\n"
            f"{cleaned_dialog[:2000]}\n\n"
        )
    if not documents:
        user_content = (
            f"{history_block}"
            f"{dialog_block}"
            f"Последняя реплика клиента:\n{query}\n\n"
            "Фрагменты базы знаний сейчас недоступны. Сформируй краткий ответ оператору "
            "по общим правилам розничного банка. В СОВЕТЕ напиши, что формулировку "
            "нужно сверить со статьёй базы знаний перед озвучиванием.\n"
            "Сформируй ответ по шаблону ОТВЕТ:/ПОДРОБНЕЕ:/СОВЕТ:."
        )
        return [
            {
                "role": "system",
                "content": (
                    SYSTEM_PROMPT
                    + "\nЕсли фрагменты базы знаний не переданы, всё равно заполни ОТВЕТ "
                    "осторожной формулировкой и укажи в СОВЕТЕ сверку с базой знаний."
                ),
            },
            {"role": "user", "content": user_content},
        ]
    primary = documents[0]
    user_content = (
        f"{history_block}"
        f"{dialog_block}"
        f"Последняя реплика клиента:\n{query}\n\n"
        f"Основная статья для ответа: [{primary['rank']}] {primary['title']}\n\n"
        f"Фрагменты выбранных баз знаний ({kb_label}):\n{context}\n\n"
        "Сформируй ответ по шаблону ОТВЕТ:/ПОДРОБНЕЕ:/СОВЕТ: строго по этим фрагментам. "
        "Если клиент уточнил детали (например, тип карты) — отрази это в ОТВЕТЕ и ПОДРОБНЕЕ. "
        "Пиши естественно и грамотно по-русски."
        + (
            "\nЭто живой звонок. ОТВЕТ — не больше трёх коротких предложений. "
            "ПОДРОБНЕЕ и СОВЕТ оставь пустыми. "
            "Если во фрагменте есть цифра, срок или условие по вопросу — "
            "назови их. Не пиши, что сведений нет, когда ответ есть в тексте."
            if brief
            else ""
        )
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_llm_text(response: Mapping[str, Any]) -> str:
    try:
        choices = response["choices"]
        message = choices[0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SuflerOrchestratorError(
            "ModelGateway returned an unexpected response shape"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise SuflerOrchestratorError("ModelGateway returned empty content")
    return content.strip()


def _log_latency(
    *,
    request_id: str,
    latency_ms: Mapping[str, float],
    hint_count: int,
    document_count: int,
) -> None:
    logger.info(
        "sufler_suggest_latency request_id=%s profile=%s kb_id=%s "
        "qu_ms=%.3f rag_ms=%.3f llm_ms=%.3f total_ms=%.3f "
        "documents=%s hints=%s",
        request_id,
        PROFILE,
        KB_ID,
        latency_ms["qu"],
        latency_ms["rag"],
        latency_ms["llm"],
        latency_ms["total"],
        document_count,
        hint_count,
    )


def _normalize_kb_slugs(kb_slugs: Sequence[str] | None) -> list[str] | None:
    if kb_slugs is None:
        return None
    return [
        slug.strip()
        for slug in kb_slugs
        if isinstance(slug, str) and slug.strip()
    ]


def _retrieve_documents(
    retrieval_text: str,
    *,
    limit: int,
    kb_slugs: list[str] | None,
) -> tuple[dict[str, Any], str]:
    """Return QU result and kb label. Selected slugs search the same catalog as AI chat."""
    if kb_slugs is None:
        result = preview_query(retrieval_text, limit=max(limit, 5), snippet_chars=2000)
        return result, KB_ID
    if not kb_slugs:
        return {"documents": []}, "none"
    from qu.assistant_retrieval import preview_assistant_query

    result = preview_assistant_query(
        retrieval_text,
        kb_slugs=kb_slugs,
        limit=max(limit, 5),
    )
    return result, ",".join(kb_slugs)


def _scenario_payload(
    progress: ScenarioProgress | None,
    *,
    paused: bool = False,
    completed: bool = False,
    return_phrase: str = "",
) -> dict[str, Any] | None:
    if progress is None:
        return None
    payload = progress.as_dict()
    payload["title"] = _safe_ru_en_text(str(payload.get("title") or ""))
    payload["path"] = [
        safe
        for item in payload.get("path") or []
        if (safe := _safe_ru_en_text(str(item)))
    ]
    payload["steps"] = [
        {
            "node_id": str(item.get("node_id") or ""),
            "label": safe,
        }
        for item in payload.get("steps") or []
        if isinstance(item, Mapping)
        and (safe := _safe_ru_en_text(str(item.get("label") or "")))
    ]
    payload["next_clarify"] = _safe_ru_en_text(
        str(payload.get("next_clarify") or "")
    )
    payload["upcoming"] = [
        {
            "node_id": str(item.get("node_id") or ""),
            "label": safe,
        }
        for item in payload.get("upcoming") or []
        if isinstance(item, Mapping)
        and (safe := _safe_ru_en_text(str(item.get("label") or "")))
    ]
    cleaned_choices: list[dict[str, str]] = []
    for item in payload.get("choices") or []:
        if not isinstance(item, Mapping):
            continue
        label = _safe_ru_en_text(str(item.get("label") or ""))
        reply = _safe_ru_en_text(str(item.get("reply") or item.get("label") or ""))
        if not label and not reply:
            continue
        cleaned_choices.append({"label": label or reply, "reply": reply or label})
    payload["choices"] = cleaned_choices
    payload["paused"] = bool(paused)
    payload["completed"] = bool(completed)
    if paused:
        spoken = _safe_ru_en_text(return_phrase)
        if not spoken:
            step = ""
            if payload.get("steps"):
                step = str(payload["steps"][-1].get("label") or "")
            clarify = str(payload.get("next_clarify") or "")
            spoken = _safe_ru_en_text(
                " ".join(
                    part
                    for part in (
                        "Вернёмся к вашему вопросу.",
                        step + "." if step else "",
                        clarify,
                    )
                    if part
                )
            )
        payload["return_phrase"] = spoken
    return payload


def _filter_scenario_choices(
    choices: Sequence[Mapping[str, Any]],
    query: str,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in choices:
        label = str(item.get("label") or "").strip()
        reply = str(item.get("reply") or label).strip()
        if not label and not reply:
            continue
        normalized.append({"label": label or reply, "reply": reply or label})
    age_known = _client_age_under_14(query)
    if age_known:
        normalized = [
            item
            for item in normalized
            if not re.search(
                r"четырнадцат|лет сам|мне уже 14|паспорт есть",
                f"{item['label']} {item['reply']}".casefold(),
            )
        ]
    if _client_asked_for_card(query):
        cardish = [
            item
            for item in normalized
            if "карт" in f"{item['label']} {item['reply']}".casefold()
        ]
        without_card = [
            item
            for item in cardish
            if re.search(r"без карт|без карточ", f"{item['label']} {item['reply']}".casefold())
        ]
        with_card = [item for item in cardish if item not in without_card]
        if with_card and without_card:
            skip = {id(item) for item in cardish}
            normalized = [item for item in normalized if id(item) not in skip]
    return normalized


_CLIENT_VOICE_OPENER = re.compile(
    r"(?i)^\s*я\s+(?:дедушк|бабушк|мама|папа|опекун|законн|не )"
)


def _operator_choice_label(item: Mapping[str, str]) -> str:
    label = str(item.get("label") or "").strip().rstrip(".!")
    reply = str(item.get("reply") or "").strip().rstrip(".!")
    if label and not _CLIENT_VOICE_OPENER.match(label):
        return label
    if reply and not _CLIENT_VOICE_OPENER.match(reply):
        return reply
    return ""


def _leading_question_from_choices(choices: Sequence[Mapping[str, str]]) -> str:
    labels = [
        piece
        for item in choices
        if (piece := _operator_choice_label(item))
    ]
    blob = " ".join(labels).casefold()
    if "законн" in blob:
        return "Вы законный представитель или нет?"
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0] if labels[0].endswith("?") else f"{labels[0]}?"
    if len(labels) == 2:
        return f"{labels[0]} или {labels[1]}?"
    listed = ", ".join(labels[:-1])
    return f"{listed} или {labels[-1]}?"


def _strip_question_sentences(text: str) -> str:
    parts = [
        part.strip()
        for part in re.split(r"(?<=[.!?…])\s+", text or "")
        if part.strip()
    ]
    kept = [part for part in parts if not part.endswith("?")]
    return " ".join(kept).strip()


def _compose_scenario_spoken(script: str, question: str) -> str:
    script = (script or "").strip()
    question = (question or "").strip()
    if question and not question.endswith("?"):
        question = question.rstrip(".!") + "?"
    if script and "?" in script:
        return script
    if not question:
        return script
    body = _strip_question_sentences(script)
    if body:
        return f"{body} {question}"
    return question


def _rewrite_scenario_phrase(
    progress: ScenarioProgress,
    query: str,
    *,
    gateway: ModelGateway | None,
    dialog_context: str = "",
    returning: bool = False,
    skip_llm: bool = False,
) -> tuple[str, str]:
    """Turn script text into a first-person operator replica. Fallback = script."""
    script = _sanitize_spoken_phrase(progress.hint_text, query)
    tip = _sanitize_spoken_phrase(progress.next_clarify, query)
    if tip and _is_internal_operator_sentence(tip):
        tip = ""
    if not script:
        script = tip
        tip = ""
    choices = _filter_scenario_choices(progress.choices, query)
    question = _leading_question_from_choices(choices) or tip
    spoken_fallback = _compose_scenario_spoken(script, question)
    fallback = (spoken_fallback or script, "")
    if not script and not question:
        return fallback
    if skip_llm or (os.environ.get("MODEL_GATEWAY_MODE") or "").strip().lower() == "stub":
        return fallback
    try:
        settings = get_model_settings(PROFILE)
        active = gateway or ModelGateway.from_registry()
        dialog_block = ""
        cleaned_dialog = dialog_context.strip() if isinstance(dialog_context, str) else ""
        if cleaned_dialog:
            dialog_block = f"Текущая переписка:\n{cleaned_dialog[:1200]}\n\n"
        user_content = (
            f"{dialog_block}"
            f"Реплика клиента:\n{query}\n\n"
            f"Скрипт узла «{progress.title}»:\n{script}\n"
        )
        if tip:
            user_content += f"\nДополнительное уточнение из сценария:\n{tip}\n"
        if choices:
            listed = "\n".join(
                f"{index}. {item['reply']}"
                for index, item in enumerate(choices, start=1)
            )
            user_content += (
                "\nВозможные ответы клиента — не читай их вслух "
                "и не строй вопрос от первого лица клиента:\n"
                f"{listed}\n"
            )
        if returning:
            user_content += (
                "\nКлиент мог забыть незакрытый вопрос. "
                "Верни разговор к этому шагу сценария одной репликой "
                "и добей то, что клиент хотел оформить. "
                "Не пересказывай весь диалог."
            )
            if choices:
                user_content += (
                    " В конце обязательно задай один наводящий вопрос "
                    "по вариантам ответа клиента."
                )
            else:
                user_content += (
                    " Задай только одно уточнение, на которое клиент ещё не ответил."
                )
        elif choices:
            user_content += (
                "\nСобери одну реплику как продолжение диалога. "
                "Не пересказывай вопрос клиента. Сначала суть из скрипта, "
                "в конце ОБЯЗАТЕЛЬНО один естественный вопрос оператора "
                "(например: вы законный представитель или нет?). "
                "Если карта уже нужна — не спрашивай "
                "«с карточкой или без». Никаких пометок про СУЗ и статьи."
            )
        else:
            user_content += (
                "\nСобери одну реплику как продолжение диалога. "
                "Это финальный шаг скрипта — не задавай новых вопросов."
            )
        response = active.chat(
            PROFILE,
            [
                {
                    "role": "system",
                    "content": (
                        SCENARIO_RETURN_PHRASE_PROMPT
                        if returning
                        else SCENARIO_PHRASE_PROMPT
                    ),
                },
                {"role": "user", "content": user_content},
            ],
            temperature=min(float(settings.temperature), 0.4),
            top_p=float(settings.top_p),
            max_tokens=min(int(settings.max_tokens), 280),
        )
        rewritten = _safe_ru_en_text(_strip_markup(_extract_llm_text(response)))
        rewritten = re.sub(r"(?is)^\s*(ответ|реплика)\s*:\s*", "", rewritten).strip()
        if len(rewritten) < 20:
            return fallback
        script_tokens = {
            token
            for token in re.findall(
                r"[а-яёa-z]{4,}",
                " ".join(
                    [script, tip, *(item["reply"] for item in choices)]
                ).casefold(),
            )
        }
        result_tokens = set(re.findall(r"[а-яёa-z]{4,}", rewritten.casefold()))
        overlap = script_tokens & result_tokens
        needed = 1 if len(script_tokens) < 4 else min(3, max(2, len(script_tokens) // 5))
        if script_tokens and len(overlap) < needed:
            return fallback
        spoken = _sanitize_spoken_phrase(rewritten, query)
        if re.search(r"(?i)\bя\s+(дедушк|бабушк|мама|папа|опекун)", spoken or rewritten):
            return fallback
        if choices:
            if "?" not in (spoken or rewritten):
                spoken = _compose_scenario_spoken(spoken or rewritten, question)
        else:
            spoken = _drop_invented_questions(spoken or rewritten)
        return spoken or rewritten, ""
    except Exception:  # noqa: BLE001 — keep the script if the model is down
        logger.exception("sufler_scenario_rewrite_failed")
        return fallback


def _suggested_payload(
    suggested: SuggestedScenario | None,
) -> dict[str, Any] | None:
    if suggested is None:
        return None
    payload = suggested.as_dict()
    payload["title"] = _safe_ru_en_text(str(payload.get("title") or ""))
    return payload


def _scenario_hint_block(progress: ScenarioProgress) -> dict[str, Any]:
    scenario_hint = _sanitize_spoken_phrase(progress.hint_text)
    scenario_tip = _safe_ru_en_text(progress.next_clarify)
    if scenario_tip and _is_internal_operator_sentence(scenario_tip):
        scenario_tip = ""
    return {
        "rank": 1,
        "text": scenario_hint,
        "operator_tip": scenario_tip,
        "source_type": "scenario",
        "relevance_score": 0.95,
        "relevance_percent": 95,
        "citations": [
            {
                "article_id": 0,
                "chunk_index": 0,
                "title": _safe_ru_en_text(progress.title)
                or "Сценарий контакт-центра",
                "permalink": "",
            }
        ],
    }


def enter_suggested_scenario(
    code: str,
    *,
    session_id: str,
    channel: str = "",
) -> dict[str, Any]:
    progress = enter_scenario(code, session_key=session_id, channel=channel)
    if progress is None or not progress.hint_text:
        raise SuflerOrchestratorError("scenario_not_available")
    block = _scenario_hint_block(progress)
    phrase, tip = _rewrite_scenario_phrase(progress, "", gateway=None)
    block["text"] = phrase or block["text"]
    block["operator_tip"] = tip
    return {
        "query": "",
        "profile": PROFILE,
        "kb_id": KB_ID,
        "kb_slugs": [],
        "hints": [block],
        "citations_enabled": True,
        "blocked_reason": None,
        "min_relevance": OPERATOR_MIN_RELEVANCE,
        "latency_ms": {"qu": 0.0, "rag": 0.0, "llm": 0.0, "total": 0.0},
        "request_id": str(uuid.uuid4()),
        "scenario": _scenario_payload(progress),
        "suggested_scenario": None,
    }


def pause_active_scenario(session_id: str) -> dict[str, Any]:
    progress = pause_scenario_session(session_id)
    return_phrase = ""
    if progress is not None:
        return_phrase, _ = _rewrite_scenario_phrase(
            progress,
            "",
            gateway=None,
            returning=True,
        )
    return {
        "ok": True,
        "scenario": _scenario_payload(
            progress,
            paused=True,
            return_phrase=return_phrase,
        ),
        "suggested_scenario": None,
    }


def clear_active_scenario(session_id: str) -> dict[str, Any]:
    clear_scenario_session(session_id)
    return {
        "ok": True,
        "scenario": None,
        "suggested_scenario": None,
    }


def resume_active_scenario(
    session_id: str,
    *,
    mode: str = "checkpoint",
    channel: str = "",
    node_id: str = "",
    dialog_context: str = "",
) -> dict[str, Any]:
    if mode not in {"start", "checkpoint", "step"}:
        raise SuflerOrchestratorError("mode must be start, checkpoint or step")
    if mode == "step" and not str(node_id or "").strip():
        raise SuflerOrchestratorError("node_id is required for step resume")
    progress = resume_scenario(
        session_id,
        mode=mode,
        channel=channel,
        node_id=node_id,
    )
    if progress is None or not progress.hint_text:
        raise SuflerOrchestratorError("scenario_not_available")
    block = _scenario_hint_block(progress)
    phrase, tip = _rewrite_scenario_phrase(
        progress,
        "",
        gateway=None,
        dialog_context=dialog_context,
        returning=True,
    )
    block["text"] = phrase or block["text"]
    block["operator_tip"] = tip
    return {
        "query": "",
        "profile": PROFILE,
        "kb_id": KB_ID,
        "kb_slugs": [],
        "hints": [block],
        "citations_enabled": True,
        "blocked_reason": None,
        "min_relevance": OPERATOR_MIN_RELEVANCE,
        "latency_ms": {"qu": 0.0, "rag": 0.0, "llm": 0.0, "total": 0.0},
        "request_id": str(uuid.uuid4()),
        "scenario": _scenario_payload(progress),
        "suggested_scenario": None,
    }


def _explicit_telephony(channel: str) -> bool:
    return (channel or "").strip().lower() in {"telephony", "phone", "sip", "call"}


def _keep_telephony_fragment(channel: str, text: str) -> bool:
    """A live ASR final often ends on a preposition. Still search the KB.

    Greetings, thanks and small-talk stay silent. Only an incomplete line
    that already has real words is kept.
    """
    if not _explicit_telephony(channel):
        return False
    reason = classify_turn(text) or ""
    if not str(reason).endswith("incomplete"):
        return False
    return bool(_query_specific_tokens(text))


def opening_scenario_hint(
    text: str,
    *,
    session_id: str = "",
    channel: str = "",
) -> dict[str, Any] | None:
    """Scenario card for the first paint. Does not advance the live session."""
    from orchestrator.scenario_engine import peek_scenario_turn

    try:
        turn = peek_scenario_turn(
            text,
            session_key=session_id,
            channel=channel,
        )
    except Exception:
        logger.exception("sufler_scenario_peek_failed")
        return None
    progress = turn.progress
    if progress is None or not str(progress.hint_text or "").strip():
        return None
    return _scenario_hint_block(progress)


def preview_hints(
    text: str,
    *,
    limit: int = 3,
    kb_slugs: Sequence[str] | None = None,
    channel: str = "",
) -> dict[str, Any]:
    """KB snippet cards only. No LLM, so the operator sees a source before DeepSeek."""
    normalized = text.strip() if isinstance(text, str) else ""
    if not normalized:
        return {"query": "", "hints": [], "blocked_reason": NO_HINT_REASON}
    if (
        is_social_turn(normalized)
        or classify_turn(normalized)
        or (
            _explicit_telephony(channel)
            and not telephony_turn_needs_hint(normalized)
        )
    ) and not _keep_telephony_fragment(channel, normalized):
        return {
            "query": normalized,
            "hints": [],
            "blocked_reason": NO_HINT_REASON,
        }
    policy = _policy_settings()
    channel_key = _normalize_channel(channel)
    min_relevance = float(policy.min_relevance_for_channel(channel_key))
    selected_slugs = _normalize_kb_slugs(kb_slugs)
    try:
        qu_result, _kb_label = _retrieve_documents(
            normalized,
            limit=limit,
            kb_slugs=selected_slugs,
        )
    except Exception:
        logger.exception("sufler_preview_failed")
        return {
            "query": normalized,
            "hints": [],
            "blocked_reason": "sufler_unavailable",
        }
    settings = get_model_settings(PROFILE)
    documents = _select_documents(
        qu_result.get("documents") or [],
        limit=limit,
        context_threshold=float(settings.context_inclusion_threshold),
        allow_weak=bool(selected_slugs),
        query=normalized,
        min_relevance=min_relevance,
    )
    if (
        documents
        and (_explicit_telephony(channel) or not selected_slugs)
        and not _document_supports_query(documents[0], normalized)
    ):
        documents = []
    hints: list[dict[str, Any]] = []
    for document in documents:
        if float(document["relevance_score"]) < min_relevance and not selected_slugs:
            continue
        hint_text = _sanitize_spoken_phrase(
            _snippet_as_answer(document, normalized),
            normalized,
        )
        if not hint_text:
            continue
        cite = bool(_answer_uses_document(hint_text, document))
        hints.append(
            _kb_hint_payload(
                rank=len(hints) + 1,
                text=hint_text,
                operator_tip="",
                document=document,
                relevance_score=document["relevance_score"],
                relevance_percent=document["relevance_percent"],
                citations=[_citation(document)] if cite else [],
                query=normalized,
            )
        )
        if len(hints) >= limit:
            break
    return {
        "query": normalized,
        "hints": hints,
        "blocked_reason": None if hints else "no_relevant_knowledge",
    }


def suggest(
    text: str,
    *,
    limit: int = DEFAULT_HINT_LIMIT,
    gateway: ModelGateway | None = None,
    request_id: str | None = None,
    client_history: str = "",
    dialog_context: str = "",
    kb_slugs: Sequence[str] | None = None,
    channel: str = "",
    mode: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Run text → QU → RAG → ModelGateway(sufler_cc) → citations."""
    normalized = text.strip() if isinstance(text, str) else ""
    if not normalized:
        raise SuflerOrchestratorError("text must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise SuflerOrchestratorError("limit must be an integer")
    if not 1 <= limit <= MAX_HINT_LIMIT:
        raise SuflerOrchestratorError(
            f"limit must be between 1 and {MAX_HINT_LIMIT}"
        )

    policy = _policy_settings()
    channel_key = _normalize_channel(channel)
    resolved_mode = _normalize_mode(mode, default=policy.default_mode)
    min_relevance = float(policy.min_relevance_for_channel(channel_key))
    limit = min(limit, max(1, int(policy.max_hints)))

    correlation_id = request_id or str(uuid.uuid4())
    total_started = time.perf_counter()
    latency_ms = {"qu": 0.0, "rag": 0.0, "llm": 0.0, "total": 0.0}
    retrieval_text = _retrieval_query(normalized, dialog_context)
    selected_slugs = _normalize_kb_slugs(kb_slugs)
    grounded_only = selected_slugs is not None
    kb_label = KB_ID

    if resolved_mode == SuflerPolicy.MODE_SERVICE:
        latency_ms["total"] = _elapsed_ms(total_started)
        _log_latency(
            request_id=correlation_id,
            latency_ms=latency_ms,
            hint_count=0,
            document_count=0,
        )
        return {
            "query": normalized,
            "profile": PROFILE,
            "kb_id": kb_label,
            "kb_slugs": selected_slugs or [],
            "hints": [],
            "citations_enabled": True,
            "blocked_reason": "service_mode",
            "min_relevance": min_relevance,
            "latency_ms": latency_ms,
            "request_id": correlation_id,
            "scenario": None,
            "suggested_scenario": None,
        }

    if is_social_turn(normalized):
        latency_ms["total"] = _elapsed_ms(total_started)
        _log_latency(
            request_id=correlation_id,
            latency_ms=latency_ms,
            hint_count=0,
            document_count=0,
        )
        return {
            "query": normalized,
            "profile": PROFILE,
            "kb_id": kb_label,
            "kb_slugs": selected_slugs or [],
            "hints": [],
            "citations_enabled": True,
            "blocked_reason": NO_HINT_REASON,
            "min_relevance": min_relevance,
            "latency_ms": latency_ms,
            "request_id": correlation_id,
            "scenario": None,
            "suggested_scenario": None,
        }

    progress: ScenarioProgress | None = None
    suggested: SuggestedScenario | None = None
    session_active = False
    unmatched = False
    paused_progress: ScenarioProgress | None = None
    try:
        turn = resolve_scenario_turn(
            normalized,
            session_key=session_id,
            channel=channel_key,
        )
        progress = turn.progress
        suggested = turn.suggested
        session_active = turn.session_active
        unmatched = turn.unmatched
        paused_progress = turn.paused_progress
    except Exception:  # noqa: BLE001 — scenario must never break suggest
        logger.exception("sufler_scenario_failed request_id=%s", correlation_id)
        progress = None

    scenario_block: dict[str, Any] | None = None
    if progress is not None:
        hint_progress = progress
        scenario_hint = _safe_ru_en_text(progress.hint_text)
        if not scenario_hint:
            from orchestrator.scenario_engine import UNMATCHED_HINT

            scenario_hint = UNMATCHED_HINT
        scenario_block = _scenario_hint_block(hint_progress)
        phrase, tip = _rewrite_scenario_phrase(
            hint_progress,
            normalized,
            gateway=gateway,
            dialog_context=dialog_context,
            skip_llm=_explicit_telephony(channel),
        )
        scenario_block["text"] = phrase or scenario_hint
        scenario_block["operator_tip"] = tip

    ordinary_call = (
        _explicit_telephony(channel)
        and not session_active
        and suggested is None
        and progress is None
        and paused_progress is None
        and not telephony_turn_needs_hint(normalized)
        and not _keep_telephony_fragment(channel, normalized)
    )
    if (
        progress is None
        and paused_progress is None
        and (session_active or classify_turn(normalized) or ordinary_call)
        and suggested is None
        and not _keep_telephony_fragment(channel, normalized)
    ):
        latency_ms["total"] = _elapsed_ms(total_started)
        _log_latency(
            request_id=correlation_id,
            latency_ms=latency_ms,
            hint_count=0,
            document_count=0,
        )
        return {
            "query": normalized,
            "profile": PROFILE,
            "kb_id": kb_label,
            "kb_slugs": selected_slugs or [],
            "hints": [],
            "citations_enabled": True,
            "blocked_reason": NO_HINT_REASON,
            "min_relevance": min_relevance,
            "latency_ms": latency_ms,
            "request_id": correlation_id,
            "scenario": None,
            "suggested_scenario": None,
        }

    def _with_scenario(kb_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if scenario_block is None:
            return kb_hints
        combined = [scenario_block]
        for item in kb_hints:
            item = dict(item)
            item["rank"] = len(combined) + 1
            combined.append(item)
        return combined

    return_phrase = ""
    if paused_progress is not None and progress is None:
        return_phrase, _ = _rewrite_scenario_phrase(
            paused_progress,
            normalized,
            gateway=gateway,
            dialog_context=dialog_context,
            returning=True,
            skip_llm=_explicit_telephony(channel),
        )
    scenario_state = _scenario_payload(
        progress,
        completed=bool(progress is not None and not session_active and not unmatched),
    ) or _scenario_payload(
        paused_progress,
        paused=True,
        return_phrase=return_phrase,
    )

    qu_started = time.perf_counter()
    try:
        qu_result, kb_label = _retrieve_documents(
            retrieval_text,
            limit=limit,
            kb_slugs=selected_slugs,
        )
    except Exception:
        logger.exception(
            "sufler_qu_failed request_id=%s",
            correlation_id,
        )
        qu_result = {"documents": []}
    latency_ms["qu"] = _elapsed_ms(qu_started)

    rag_started = time.perf_counter()
    settings = get_model_settings(PROFILE)
    context_threshold = float(settings.context_inclusion_threshold)

    documents = _select_documents(
        qu_result["documents"],
        limit=limit,
        context_threshold=context_threshold,
        allow_weak=bool(selected_slugs),
        query=retrieval_text,
        min_relevance=min_relevance,
    )
    if (
        documents
        and (_explicit_telephony(channel) or not selected_slugs)
        and not _document_supports_query(documents[0], normalized)
    ):
        documents = []
    latency_ms["rag"] = _elapsed_ms(rag_started)

    if not documents:
        # Empty index or nothing above the policy relevance floor.
        empty_reason = (
            "sufler_unavailable"
            if not qu_result.get("documents")
            else "no_relevant_knowledge"
        )
        if scenario_block:
            latency_ms["total"] = _elapsed_ms(total_started)
            _log_latency(
                request_id=correlation_id,
                latency_ms=latency_ms,
                hint_count=1,
                document_count=0,
            )
            return {
                "query": normalized,
                "profile": PROFILE,
                "kb_id": kb_label,
                "kb_slugs": selected_slugs or [],
                "hints": [scenario_block],
                "citations_enabled": True,
                "blocked_reason": None,
                "min_relevance": min_relevance,
                "latency_ms": latency_ms,
                "request_id": correlation_id,
                "scenario": scenario_state,
                "suggested_scenario": _suggested_payload(suggested),
            }
        if len(_query_specific_tokens(normalized)) < 2 and not _keep_telephony_fragment(
            channel, normalized
        ):
            latency_ms["total"] = _elapsed_ms(total_started)
            _log_latency(
                request_id=correlation_id,
                latency_ms=latency_ms,
                hint_count=0,
                document_count=0,
            )
            return {
                "query": normalized,
                "profile": PROFILE,
                "kb_id": kb_label,
                "kb_slugs": selected_slugs or [],
                "hints": [],
                "citations_enabled": True,
                "blocked_reason": NO_HINT_REASON,
                "min_relevance": min_relevance,
                "latency_ms": latency_ms,
                "request_id": correlation_id,
                "scenario": scenario_state,
                "suggested_scenario": _suggested_payload(suggested),
            }
        if _explicit_telephony(channel) and telephony_turn_needs_hint(normalized):
            latency_ms["total"] = _elapsed_ms(total_started)
            _log_latency(
                request_id=correlation_id,
                latency_ms=latency_ms,
                hint_count=0,
                document_count=0,
            )
            return {
                "query": normalized,
                "profile": PROFILE,
                "kb_id": kb_label,
                "kb_slugs": selected_slugs or [],
                "hints": [],
                "citations_enabled": True,
                "blocked_reason": empty_reason,
                "min_relevance": min_relevance,
                "latency_ms": latency_ms,
                "request_id": correlation_id,
                "scenario": scenario_state,
                "suggested_scenario": _suggested_payload(suggested),
            }
        skip_ungrounded = grounded_only or (
            not _allow_ungrounded() and not ignored_suz_fixtures_exist()
        )
        if skip_ungrounded:
            latency_ms["total"] = _elapsed_ms(total_started)
            _log_latency(
                request_id=correlation_id,
                latency_ms=latency_ms,
                hint_count=0,
                document_count=0,
            )
            return {
                "query": normalized,
                "profile": PROFILE,
                "kb_id": kb_label,
                "kb_slugs": selected_slugs or [],
                "hints": [],
                "citations_enabled": True,
                "blocked_reason": empty_reason,
                "min_relevance": min_relevance,
                "latency_ms": latency_ms,
                "request_id": correlation_id,
                "scenario": scenario_state,
                "suggested_scenario": _suggested_payload(suggested),
            }

    llm_started = time.perf_counter()
    used_source = False
    detail_text = ""
    answer_text = ""
    operator_tip = ""
    active_gateway = gateway or ModelGateway.from_registry()
    # Live call: one short reply. A long «подробнее» block keeps the card loading.
    brief = _explicit_telephony(channel)
    answer_model = ""
    if brief:
        try:
            from hub.model_catalog import SLOT_ANSWER, selected_model

            answer_model = selected_model(SLOT_ANSWER)
        except Exception:
            answer_model = ""
    try:
        chat_kwargs: dict[str, Any] = {
            "temperature": float(settings.temperature),
            "top_p": float(settings.top_p),
            "max_tokens": 200 if brief else max(int(settings.max_tokens), 720),
        }
        if answer_model:
            chat_kwargs["runtime_model"] = answer_model
        llm_response = active_gateway.chat(
            PROFILE,
            _build_messages(
                normalized,
                documents,
                client_history=client_history,
                dialog_context=dialog_context,
                kb_label=kb_label,
                brief=brief,
            ),
            **chat_kwargs,
        )
        llm_text = _extract_llm_text(llm_response)
        char_limit = 320 if brief else max(int(settings.response_chars_max), 400)
        answer_text, operator_tip, detail_text = _parse_llm_hint(llm_text)
        cleaned = _clean_answer_text(answer_text)
        answer_text = complete_sentences(cleaned, max_chars=char_limit)
        operator_tip = _safe_ru_en_text(operator_tip)
        used_source = bool(documents) and _answer_uses_document(
            answer_text, documents[0]
        )
        if documents and not used_source:
            grounded = _snippet_as_answer(documents[0], normalized)
            if grounded:
                answer_text = grounded
                used_source = True
        parsed_detail = _finalize_detail_text(detail_text, spoken="")
        if (
            documents
            and not brief
            and (not parsed_detail or len(parsed_detail) < len(answer_text) + 60)
        ):
            parsed_detail = _finalize_detail_text(
                _expand_kb_detail_llm(
                    query=normalized,
                    spoken=answer_text,
                    document=documents[0],
                    gateway=active_gateway,
                    settings=settings,
                ),
                spoken="",
            )
        detail_text = parsed_detail
    except Exception:  # noqa: BLE001 — fall back to KB snippets
        logger.exception("sufler_llm_failed request_id=%s", correlation_id)
        answer_text, operator_tip, detail_text = "", "", ""
        latency_ms["llm"] = _elapsed_ms(llm_started)
    else:
        latency_ms["llm"] = _elapsed_ms(llm_started)

    if not answer_text:
        if documents:
            answer_text = _snippet_as_answer(documents[0], normalized)
            used_source = bool(answer_text) and _answer_uses_document(
                answer_text, documents[0]
            )
        if not answer_text:
            answer_text = (
                "В выбранных базах знаний нет подходящей статьи по этой реплике. "
                "Оформите продукт в отделении с паспортом либо через "
                "интернет-банк / мобильное приложение. Перед ответом "
                "сверьте актуальные условия в базе знаний."
            )
            operator_tip = operator_tip or "Сверить формулировку со статьёй базы знаний."

    hints: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        if float(document["relevance_score"]) < min_relevance and not selected_slugs:
            continue
        if index == 0:
            hint_text = answer_text
            tip = operator_tip
            cite = used_source
            extra_detail = detail_text
        else:
            hint_text = _snippet_as_answer(document, normalized)
            tip = ""
            cite = bool(hint_text) and _answer_uses_document(hint_text, document)
            extra_detail = ""
        hint_text = _sanitize_spoken_phrase(hint_text, normalized)
        tip = _safe_ru_en_text(tip)
        if not hint_text:
            continue
        hints.append(
            _kb_hint_payload(
                rank=len(hints) + 1,
                text=hint_text,
                operator_tip=tip,
                document=document,
                relevance_score=document["relevance_score"],
                relevance_percent=document["relevance_percent"],
                citations=[_citation(document)] if cite else [],
                detail_text=extra_detail,
                query=normalized,
            )
        )
    answer_text = _safe_ru_en_text(answer_text)
    operator_tip = _safe_ru_en_text(operator_tip)
    if answer_text and not hints:
        source = documents[0] if documents else None
        source_score = float(source["relevance_score"]) if source else 0.5
        if source is None or source_score >= min_relevance or selected_slugs:
            hints.append(
                _kb_hint_payload(
                    rank=1,
                    text=answer_text,
                    operator_tip=operator_tip,
                    document=source,
                    detail_text=detail_text,
                    query=normalized,
                    relevance_score=source_score,
                    relevance_percent=(
                        int(source["relevance_percent"]) if source else 50
                    ),
                    citations=(
                        [_citation(source)]
                        if source and _answer_uses_document(answer_text, source)
                        else []
                    ),
                )
            )
    hints = _with_scenario(hints)
    if not hints:
        latency_ms["total"] = _elapsed_ms(total_started)
        _log_latency(
            request_id=correlation_id,
            latency_ms=latency_ms,
            hint_count=0,
            document_count=len(documents),
        )
        return {
            "query": normalized,
            "profile": PROFILE,
            "kb_id": kb_label,
            "kb_slugs": selected_slugs or [],
            "hints": [],
            "citations_enabled": True,
            "blocked_reason": "no_relevant_knowledge",
            "min_relevance": min_relevance,
            "latency_ms": latency_ms,
            "request_id": correlation_id,
            "scenario": scenario_state,
            "suggested_scenario": _suggested_payload(suggested),
        }

    latency_ms["total"] = _elapsed_ms(total_started)
    _log_latency(
        request_id=correlation_id,
        latency_ms=latency_ms,
        hint_count=len(hints),
        document_count=len(documents),
    )
    return {
        "query": normalized,
        "profile": PROFILE,
        "kb_id": kb_label,
        "kb_slugs": selected_slugs or [],
        "hints": hints,
        "citations_enabled": True,
        "blocked_reason": None,
        "min_relevance": min_relevance,
        "latency_ms": latency_ms,
        "request_id": correlation_id,
        "gateway_model": _runtime_model_or_empty(active_gateway),
        "scenario": scenario_state,
        "suggested_scenario": _suggested_payload(suggested),
    }
