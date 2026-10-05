"""Read-only Query Understanding preview service for FR-UND-12."""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from django.db import connection
from django.db.models import Q
from pgvector.django import CosineDistance

from hub.model_registry_store import get_model_settings
from ingest.models import CCProductionChunk
from core.embeddings import embed_query, embed_query_with_backend
from qu.models import QuReferenceExample


DEFAULT_LIMIT = 5
MAX_LIMIT = 5
MAX_CHUNKS_PER_ARTICLE = 3
EXAMPLE_MATCH_FLOOR = 0.52
MIN_EXAMPLE_OVERLAP = 3
_TOKEN_RE = re.compile(r"[а-яёa-z]{3,}|[0-9]{2,}", re.IGNORECASE)
_NUMBER_QUERY_RE = re.compile(
    r"скольк|лет\b|дн(ей|я|ь)|месяц|час|срок|возраст|процент",
    re.IGNORECASE,
)
_PUBLIC_CONTACT_QUERY_RE = re.compile(
    r"контакт(?!-центр)|телефон|горяч\w*\s+лин|справочн|головн\w*\s+офис|"
    r"адрес\w*\s+(?:офис|банк)|юридическ\w*\s+адрес",
    re.IGNORECASE,
)
_PHONE_FACT_RE = re.compile(
    r"\+375|\b147\b|\b\d{3}\s\d{2}\s\d{2}\s\d{2}\b",
    re.IGNORECASE,
)
# «30 календарных дней», «5 рабочих дней», «дети до 23 лет»
_AGE_FACT_RE = re.compile(
    r"\b\d{1,3}(?:\s+[а-яё-]{2,}){0,3}\s+"
    r"(?:лет|год(?:а|ов)?|день|дня|дней|месяц(?:а|ев)?|час(?:а|ов)?)\b",
    re.IGNORECASE,
)
_STOPWORDS = frozenset(
    {
        "как",
        "что",
        "это",
        "для",
        "при",
        "или",
        "чем",
        "его",
        "они",
        "мы",
        "вы",
        "на",
        "по",
        "со",
        "из",
        "от",
        "до",
        "не",
        "ни",
        "же",
        "ли",
        "бы",
        "то",
        "да",
        "за",
        "без",
        "про",
        "между",
    }
)


_VERB_PREFIXES = (
    "пере",
    "пред",
    "при",
    "про",
    "под",
    "над",
    "раз",
    "рас",
    "за",
    "по",
    "вы",
    "от",
    "об",
    "из",
    "ис",
)


def _stem(token: str) -> str:
    """Collapse RU inflections so «карта/карту» and «кредит/кредитная» still match."""
    if token.isdigit() or len(token) <= 4:
        return token
    return token[:4]


def _core(token: str) -> str:
    for prefix in _VERB_PREFIXES:
        rest = token[len(prefix) :]
        if token.startswith(prefix) and len(rest) >= 4:
            return rest
    return token


def _fold_ru(text: str) -> str:
    """Case-fold and treat ё as е so «приём» matches «прием»."""
    return (text or "").casefold().replace("ё", "е")


_QUERY_EXPAND = (
    (re.compile(r"матпомощ\w*", re.IGNORECASE), " материальная помощь "),
    (re.compile(r"мат\.?\s*помощ\w*", re.IGNORECASE), " материальная помощь "),
    (
        re.compile(r"горяч\w*\s+лин\w*", re.IGNORECASE),
        " справочный номер 147 обратная связь ",
    ),
    (
        re.compile(r"головн\w*\s+офис\w*", re.IGNORECASE),
        " юридический адрес минск ",
    ),
)


def expand_user_query(text: str) -> str:
    """«матпомощь» → «материальная помощь» so lexical search hits the regulation."""
    out = text or ""
    for pattern, repl in _QUERY_EXPAND:
        out = pattern.sub(repl, out)
    return out


def _tokens(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TOKEN_RE.findall(_fold_ru(expand_user_query(text))):
        if token in _STOPWORDS:
            continue
        tokens.add(_stem(token))
        tokens.add(_stem(_core(token)))
    return tokens


def focused_snippet(content: str, query: str, size: int = 800) -> str:
    """Prefer the window that answers the query (e.g. «23 лет»), not a form header."""
    text = content or ""
    if not text:
        return ""
    query_tokens = _tokens(query)
    wants_number = bool(_NUMBER_QUERY_RE.search(query or ""))
    window_size = min(max(size, 120), max(len(text), 120))

    def score_at(start: int) -> float:
        window = text[start : start + window_size]
        window_tokens = _tokens(window)
        overlap = len(query_tokens & window_tokens)
        score = float(overlap)
        if overlap >= 3:
            score += 1.5
        if wants_number and _AGE_FACT_RE.search(window):
            score += 4.0
        elif wants_number and re.search(r"\d{2,}", window):
            score += 1.0
        if _PUBLIC_CONTACT_QUERY_RE.search(query or "") and (
            _PHONE_FACT_RE.search(window) or "147" in window
        ):
            score += 5.0
        underscores = window.count("_")
        if underscores >= 8:
            score -= min(5.0, underscores / 6.0)
        return score

    last = max(1, len(text) - window_size + 1)
    step = max(32, window_size // 8)
    best_start = 0
    best_score = score_at(0)
    for start in range(0, last, step):
        current = score_at(start)
        if current > best_score:
            best_score = current
            best_start = start

    haystack = text.casefold()
    seen: set[int] = set()
    for token in query_tokens:
        if len(token) < 3:
            continue
        idx = 0
        while True:
            found = haystack.find(token, idx)
            if found < 0:
                break
            start = max(0, found - window_size // 5)
            if start not in seen:
                seen.add(start)
                current = score_at(start)
                if current > best_score:
                    best_score = current
                    best_start = start
            idx = found + len(token)

    return text[best_start : best_start + window_size]


def complete_sentences(text: str, *, max_chars: int = 900) -> str:
    """Keep whole sentences so operator hints are not cut mid-phrase."""
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    cut = cleaned[:max_chars]
    last = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("… "))
    if last >= max_chars // 4:
        return cut[: last + 1].strip()
    last_dot = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"))
    if last_dot >= max_chars // 4:
        return cut[: last_dot + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


def extractive_answer(content: str, query: str, *, max_chars: int = 900) -> str:
    """Build a grounded hint from the matching clause, not the file header."""
    cleaned = re.sub(r"_{3,}", " ", content or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    sentences = [
        piece.strip()
        for piece in re.split(r"(?<=[.!?…])\s+", cleaned)
        if piece.strip()
    ]
    query_tokens = _tokens(query)
    wants_number = bool(_NUMBER_QUERY_RE.search(query or ""))

    def sentence_score(sentence: str) -> float:
        overlap = len(query_tokens & _tokens(sentence))
        score = float(overlap)
        if overlap >= 3:
            score += 1.5
        if wants_number and _AGE_FACT_RE.search(sentence):
            score += 4.0
        elif wants_number and re.search(r"\d{2,}", sentence):
            score += 1.0
        underscores = sentence.count("_")
        if underscores >= 3:
            score -= min(6.0, underscores / 3.0)
        return score

    if sentences and query_tokens:
        ranked_idx = sorted(
            range(len(sentences)),
            key=lambda index: -sentence_score(sentences[index]),
        )
        best_index = ranked_idx[0]
        if sentence_score(sentences[best_index]) > 0:
            chosen = [sentences[best_index]]
            total = len(chosen[0])
            neighbors = [best_index + 1]
            if not (wants_number and _AGE_FACT_RE.search(chosen[0])):
                neighbors.insert(0, best_index - 1)
            for neighbor in neighbors:
                if neighbor < 0 or neighbor >= len(sentences):
                    continue
                piece = sentences[neighbor]
                if piece.count("_") >= 3:
                    continue
                if sentence_score(piece) < 1:
                    continue
                if total + 1 + len(piece) > max_chars:
                    continue
                if neighbor < best_index:
                    chosen.insert(0, piece)
                else:
                    chosen.append(piece)
                total += 1 + len(piece)
            return complete_sentences(" ".join(chosen), max_chars=max_chars)

    window = focused_snippet(cleaned, query, size=max(max_chars, 520))
    return complete_sentences(window, max_chars=max_chars)


def training_example_score(query: str, example: QuReferenceExample) -> float:
    """Jaccard of stems. A short etalon must not steal unrelated credit questions."""
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    parts = [example.question or ""]
    if example.synonyms:
        parts.extend(
            part.strip()
            for part in re.split(r"[,;]", example.synonyms)
            if part.strip()
        )
    best = 0.0
    for part in parts:
        example_tokens = _tokens(part)
        if not example_tokens:
            continue
        overlap = query_tokens & example_tokens
        if len(overlap) < MIN_EXAMPLE_OVERLAP:
            continue
        union = query_tokens | example_tokens
        best = max(best, len(overlap) / len(union))
    return best


def matching_training_examples(
    query: str,
    *,
    floor: float = EXAMPLE_MATCH_FLOOR,
) -> list[tuple[float, QuReferenceExample]]:
    matches: list[tuple[float, QuReferenceExample]] = []
    for example in QuReferenceExample.objects.filter(is_active=True):
        if example.article_id is None:
            continue
        score = training_example_score(query, example)
        if score >= floor:
            matches.append((score, example))
    matches.sort(key=lambda item: -item[0])
    return matches


def boost_chunks_with_examples(
    scored: list[tuple[float, Any]],
    query: str,
    extra_chunks: Iterable[Any],
) -> list[tuple[float, Any]]:
    """Pin articles linked by approved etalons when the query matches the example."""
    matches = matching_training_examples(query)
    if not matches:
        return scored
    best_score, best_example = matches[0]
    pin_by_article = {
        int(best_example.article_id): round(0.55 + 0.4 * best_score, 4)
    }
    by_key: dict[tuple[int, int], tuple[float, Any]] = {}
    originals: dict[tuple[int, int], float] = {}
    for score, chunk in scored:
        key = (int(chunk.article_id), int(getattr(chunk, "chunk_index", 0)))
        originals[key] = float(score)
        by_key[key] = (float(score), chunk)
    for chunk in extra_chunks:
        article_id = int(chunk.article_id)
        if article_id not in pin_by_article:
            continue
        key = (article_id, int(getattr(chunk, "chunk_index", 0)))
        originals.setdefault(key, 0.0)
        by_key[key] = (originals[key], chunk)
    for key, (_score, chunk) in list(by_key.items()):
        article_id = int(chunk.article_id)
        pin = pin_by_article.get(article_id)
        if pin is None:
            continue
        original = originals.get(key, 0.0)
        # Keep the article on top, but do not flatten chunks to the same score —
        # otherwise preview/sufler keep the form header instead of «23 лет».
        by_key[key] = (round(min(1.0, pin + 0.05 * original), 4), chunk)
    return sorted(
        by_key.values(),
        key=lambda item: (
            -item[0],
            item[1].article_id,
            getattr(item[1], "chunk_index", 0),
        ),
    )


def _lexical_score(query: str, title: str, content: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    title_tokens = _tokens(title)
    doc_tokens = title_tokens | _tokens(content)
    if not doc_tokens:
        return 0.0
    overlap = query_tokens & doc_tokens
    if not overlap:
        return 0.0
    recall = len(overlap) / len(query_tokens)
    title_hits = query_tokens & title_tokens
    title_bonus = 0.2 * (len(title_hits) / len(query_tokens))
    return min(1.0, recall + title_bonus)


_DISTINCTIVE_MIN = 5
_TOPICAL_WINDOW = 1000
_QUERY_FILLERS = frozenset(
    {
        "какие",
        "какой",
        "какая",
        "какое",
        "какому",
        "каким",
        "каких",
        "сколько",
        "скольки",
        "почему",
        "зачем",
        "куда",
        "откуда",
        "можно",
        "нужно",
        "необходимо",
        "скажите",
        "подскажите",
    }
)


def _distinctive_terms(query: str) -> list[str]:
    """Longer query words (prefixes) — «командировке», not «при/для»."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in _TOKEN_RE.findall(_fold_ru(expand_user_query(query))):
        if (
            token in _STOPWORDS
            or token in _QUERY_FILLERS
            or len(token) < _DISTINCTIVE_MIN
        ):
            continue
        key = token[:6]
        if key in seen:
            continue
        seen.add(key)
        terms.append(key)
    return terms


# Words that sit in almost every HR file and must not decide which one answers.
_LOOKUP_SKIP_PREFIXES = (
    "банк",
    "рабо",
    "клие",
    "поло",
    "наст",
    "пункт",
    "котор",
    "такж",
    "толь",
    "если",
    "когд",
)
# «стаж» is the tenure fact; «стажировка» is a different word.
_LOOKUP_REJECT_WORDS = {
    "стаж": ("стажир",),
}


def _lookup_terms(query: str) -> list[str]:
    """Short stems of the words that identify the answering clause.

    Includes 4-letter facts such as «стаж», which distinctive-term ranking skips.
    Generic file words («банк», «работник») are left out so they cannot
    promote every HR regulation equally.
    """
    raw: list[str] = []
    for token in _TOKEN_RE.findall(_fold_ru(expand_user_query(query))):
        if token in _STOPWORDS or token in _QUERY_FILLERS or len(token) < 4:
            continue
        if any(token.startswith(prefix) for prefix in _LOOKUP_SKIP_PREFIXES):
            continue
        raw.append(token)
    raw.sort(key=len, reverse=True)
    terms: list[str] = []
    seen: set[str] = set()
    for token in raw:
        key = token if len(token) <= 4 else token[:4]
        if key in seen:
            continue
        seen.add(key)
        terms.append(key)
        if len(terms) >= 5:
            break
    return terms


def _lookup_hit_count(query: str, text: str) -> int:
    """How many lookup stems occur as their own word, not inside a longer one."""
    blob = _fold_ru(text)
    count = 0
    for term in _lookup_terms(query):
        for match in re.finditer(rf"(?<!\w){re.escape(term)}", blob):
            word = re.split(r"\W", blob[match.start() :], maxsplit=1)[0]
            rejected = any(
                word.startswith(prefix)
                for prefix in _LOOKUP_REJECT_WORDS.get(term, ())
            )
            if not rejected:
                count += 1
                break
    return count


def _term_coverage(terms: Sequence[str], text: str) -> float:
    if not terms:
        return 0.0
    blob = _fold_ru(text)
    return sum(1 for term in terms if term in blob) / len(terms)


def _best_window_coverage(
    terms: Sequence[str],
    content: str,
    *,
    window: int = _TOPICAL_WINDOW,
) -> float:
    """Score a local window so a 80k dump cannot harvest every query word."""
    text = content or ""
    if not text or not terms:
        return 0.0
    if len(text) <= window:
        return _term_coverage(terms, text)
    best = 0.0
    step = max(160, window // 2)
    last = max(1, len(text) - window + 1)
    for start in range(0, last, step):
        best = max(best, _term_coverage(terms, text[start : start + window]))
        if best >= 0.999:
            return 1.0
    return best


def _phrase_bonus(query: str, text: str) -> float:
    words = [
        token
        for token in _TOKEN_RE.findall(_fold_ru(query))
        if token not in _STOPWORDS
    ]
    blob = _fold_ru(text)
    hits = 0
    for index in range(len(words) - 1):
        phrase = f"{words[index]} {words[index + 1]}"
        if phrase in blob:
            hits += 1
    return min(0.16, 0.08 * hits)


def topical_relevance_score(
    query: str,
    title: str,
    content: str,
    extra: str = "",
) -> float:
    """Prefer a focused passage + file/KB title over a long unrelated dump."""
    terms = _distinctive_terms(query)
    heading = f"{title} {extra}"
    if not terms:
        return _lexical_score(query, title, content)
    window_cover = _best_window_coverage(terms, content)
    rare = [term for term in terms if len(term) >= 6]
    rare_cover = _best_window_coverage(rare, content) if rare else window_cover
    heading_cover = _term_coverage(terms, heading)
    lexical = _lexical_score(query, title, content)
    phrase = _phrase_bonus(query, f"{heading}\n{content}")
    return min(
        1.0,
        0.40 * window_cover
        + 0.28 * rare_cover
        + 0.18 * heading_cover
        + 0.10 * lexical
        + phrase,
    )


def _score_lexical(
    chunks: Iterable[CCProductionChunk],
    query: str,
) -> list[tuple[float, CCProductionChunk]]:
    scored: list[tuple[float, CCProductionChunk]] = []
    for chunk in chunks:
        score = _lexical_score(query, chunk.title, chunk.content)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: (-item[0], item[1].article_id))
    return scored


def suz_transfer_commission_fixture_q() -> Q:
    """INT/demo webhook articles that must never enter operator retrieval."""
    return (
        Q(title__icontains="Komissiya za perevod")
        | Q(title__icontains="комиссия за перевод")
        | Q(title__icontains="accepted sample")
        | Q(title__icontains="INT-07")
        | Q(permalink__icontains="komissiya-perevod")
        | Q(permalink__icontains="accepted-sample")
        | Q(content__icontains="Komissiya za perevod mezhdu schetami")
        | Q(content__icontains="Valid webhook body for INT-07")
    )


def is_suz_transfer_commission_doc(document: Mapping[str, Any]) -> bool:
    title = str(document.get("title") or "").casefold()
    permalink = str(document.get("permalink") or "").casefold()
    snippet = str(
        document.get("snippet") or document.get("content") or ""
    ).casefold()
    return (
        "komissiya za perevod" in title
        or "комиссия за перевод" in title
        or "accepted sample" in title
        or "int-07" in title
        or "komissiya-perevod" in permalink
        or "accepted-sample" in permalink
        or "komissiya za perevod mezhdu schetami" in snippet
        or "valid webhook body for int-07" in snippet
    )


def ignored_suz_fixtures_exist() -> bool:
    return (
        CCProductionChunk.objects.filter(is_active=True)
        .filter(suz_transfer_commission_fixture_q())
        .exists()
    )


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def _best_example(
    query_embedding: Sequence[float],
    examples: Iterable[QuReferenceExample],
    *,
    fallback: str,
) -> tuple[int | None, str]:
    ranked = [
        (
            _cosine_similarity(
                query_embedding,
                embed_query(example.question),
            ),
            example,
        )
        for example in examples
    ]
    if not ranked:
        return None, fallback
    _, best = max(ranked, key=lambda item: item[0])
    return best.pk, best.question


def preview_query(
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    snippet_chars: int = 240,
) -> dict[str, Any]:
    """Rank active KB documents and attach the source QU example."""
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must be a non-empty string")
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")

    query_embedding, backend = embed_query_with_backend(normalized_query)
    chunk_query = (
        CCProductionChunk.objects.filter(is_active=True)
        .exclude(suz_transfer_commission_fixture_q())
        .only(
            "article_id",
            "chunk_index",
            "title",
            "content",
            "permalink",
            "embedding",
        )
    )
    if backend in {"http-fallback", "lexical"}:
        scored_chunks = _score_lexical(chunk_query, normalized_query)[: limit * 20]
    elif connection.vendor == "postgresql":
        chunks = list(
            chunk_query.annotate(
                distance=CosineDistance("embedding", query_embedding)
            ).order_by("distance", "article_id")[: limit * 20]
        )
        scored_chunks = [
            (
                max(
                    max(0.0, min(1.0, 1.0 - float(chunk.distance))),
                    _lexical_score(normalized_query, chunk.title, chunk.content),
                ),
                chunk,
            )
            for chunk in chunks
        ]
    else:
        chunks = list(chunk_query)
        scored_chunks = [
            (
                max(
                    _cosine_similarity(query_embedding, list(chunk.embedding)),
                    _lexical_score(normalized_query, chunk.title, chunk.content),
                ),
                chunk,
            )
            for chunk in chunks
        ]
    examples = list(QuReferenceExample.objects.filter(is_active=True))
    examples_by_article: dict[int, list[QuReferenceExample]] = {}
    global_examples: list[QuReferenceExample] = []
    for example in examples:
        if example.article_id is None:
            global_examples.append(example)
        else:
            examples_by_article.setdefault(int(example.article_id), []).append(
                example
            )
    matched_examples = matching_training_examples(normalized_query)
    extra_ids = (
        [int(matched_examples[0][1].article_id)] if matched_examples else []
    )
    extra_chunks = (
        CCProductionChunk.objects.filter(is_active=True, article_id__in=extra_ids)
        if extra_ids
        else []
    )
    scored_chunks = boost_chunks_with_examples(
        scored_chunks,
        normalized_query,
        extra_chunks,
    )

    grouped: dict[int, list[tuple[float, CCProductionChunk]]] = {}
    for score, chunk in scored_chunks:
        grouped.setdefault(int(chunk.article_id), []).append((score, chunk))
    ranked: list[tuple[float, CCProductionChunk, str]] = []
    for article_id, items in grouped.items():
        items.sort(key=lambda item: (-item[0], item[1].chunk_index))
        selected = items[:MAX_CHUNKS_PER_ARTICLE]
        selected.sort(key=lambda item: item[1].chunk_index)
        score = max(item[0] for item in selected)
        content = "\n".join(item[1].content or "" for item in selected)
        ranked.append((score, selected[0][1], content))
    ranked.sort(key=lambda item: (-item[0], item[1].article_id))
    ranked = ranked[:limit]
    threshold = get_model_settings(
        "assistant_bank"
    ).context_inclusion_threshold
    documents = []
    preview = max(240, int(snippet_chars))
    for rank, (score, chunk, content) in enumerate(ranked, start=1):
        article_examples = examples_by_article.get(int(chunk.article_id), [])
        pinned = max(
            article_examples,
            key=lambda example: training_example_score(normalized_query, example),
            default=None,
        )
        if pinned and training_example_score(normalized_query, pinned) >= EXAMPLE_MATCH_FLOOR:
            matched_example_id, matched_example = pinned.pk, pinned.question
        elif backend in {"http-fallback", "lexical"}:
            matched_example_id, matched_example = None, chunk.title
        else:
            matched_example_id, matched_example = _best_example(
                query_embedding,
                article_examples or global_examples,
                fallback=chunk.title,
            )
        documents.append(
            {
                "rank": rank,
                "article_id": chunk.article_id,
                "chunk_index": chunk.chunk_index,
                "title": chunk.title,
                "permalink": chunk.permalink,
                "snippet": focused_snippet(content, normalized_query, preview),
                "content": content,
                "relevance_score": round(score, 4),
                "relevance_percent": round(score * 100),
                "meets_min_relevance": score >= threshold,
                "matched_example_id": matched_example_id,
                "matched_example": matched_example,
            }
        )

    hint = None
    if documents:
        top = documents[0]
        hint_text = extractive_answer(str(top.get("content") or ""), normalized_query)
        if hint_text:
            hint = {
                "text": hint_text,
                "title": top["title"],
                "permalink": top.get("permalink") or "",
                "article_id": top["article_id"],
                "relevance_percent": top["relevance_percent"],
            }

    return {
        "query": normalized_query,
        "kb_id": "cc_production",
        "min_relevance": threshold,
        "min_relevance_percent": round(threshold * 100),
        "documents": documents,
        "hint": hint,
    }
