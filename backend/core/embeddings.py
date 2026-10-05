"""Embedding router: stub (dev/tests) | HTTP service | in-process local model.

Vector size stays 1024 to match pgvector ``VectorField(dimensions=1024)`` and
the registry baseline ``intfloat/multilingual-e5-large``.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from functools import lru_cache
from typing import Literal, Sequence

import requests

logger = logging.getLogger(__name__)
_http_stub_fallback_logged = False
_query_cache: dict[tuple[str, str, str], tuple[list[float], str]] = {}
_QUERY_CACHE_MAX = 512

DEFAULT_DIMENSIONS = 1024
DEFAULT_MODEL = "intfloat/multilingual-e5-large"
SUPPORTED_MODES = frozenset({"stub", "http", "local", "lexical"})


class EmbeddingError(RuntimeError):
    """Raised when a real embedding backend fails."""


def _mode() -> str:
    raw = (os.environ.get("EMBEDDING_MODE") or "stub").strip().lower()
    return raw if raw in SUPPORTED_MODES else "stub"


def _dimensions() -> int:
    try:
        value = int(os.environ.get("EMBEDDING_DIMENSIONS") or DEFAULT_DIMENSIONS)
    except ValueError:
        return DEFAULT_DIMENSIONS
    return value if value > 0 else DEFAULT_DIMENSIONS


def _model_name() -> str:
    return (os.environ.get("EMBEDDING_MODEL") or DEFAULT_MODEL).strip()


def deterministic_embedding(
    text: str,
    dimensions: int = DEFAULT_DIMENSIONS,
) -> list[float]:
    """Offline deterministic embedding stub with pgvector-compatible shape."""
    vector = [0.0] * dimensions
    for token in text.casefold().split():
        digest = hashlib.blake2b(
            token.encode("utf-8"),
            digest_size=8,
        ).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += -1.0 if digest[4] & 1 else 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        return [value / norm for value in vector]
    return vector


def _with_e5_prefix(text: str, *, is_query: bool) -> str:
    stripped = text.strip()
    lowered = stripped.casefold()
    if lowered.startswith("query:") or lowered.startswith("passage:"):
        return stripped
    prefix = "query: " if is_query else "passage: "
    return f"{prefix}{stripped}"


def _http_embed(
    texts: Sequence[str],
    *,
    is_query: bool,
) -> list[list[float]]:
    base = (os.environ.get("EMBEDDING_BASE_URL") or "").rstrip("/")
    if not base:
        raise EmbeddingError(
            "EMBEDDING_BASE_URL is required when EMBEDDING_MODE=http"
        )
    configured_timeout = float(
        os.environ.get("EMBEDDING_TIMEOUT_SECONDS") or "15"
    )
    items = list(texts)
    # One replica must stay fast. Caching many scenario profiles may take longer.
    per_request = 2 if len(items) > 2 else len(items) or 1
    timeout = min(max(configured_timeout, 1.0), 20.0 if per_request <= 2 else 90.0)
    encoded: list[list[float]] = []
    for start in range(0, len(items) or 1, per_request):
        chunk = items[start : start + per_request]
        encoded.extend(_http_embed_once(base, chunk, is_query=is_query, timeout=timeout))
    return encoded


def _http_embed_once(
    base: str,
    texts: list[str],
    *,
    is_query: bool,
    timeout: float,
) -> list[list[float]]:
    payload = {
        "texts": texts,
        "is_query": is_query,
        "model": _model_name(),
    }
    try:
        response = requests.post(
            f"{base}/embed",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise EmbeddingError("HTTP embedding request failed") from exc
    vectors = body.get("embeddings") if isinstance(body, dict) else None
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EmbeddingError("HTTP embedding response shape is invalid")
    dims = _dimensions()
    normalized: list[list[float]] = []
    for item in vectors:
        if not isinstance(item, list) or len(item) != dims:
            raise EmbeddingError(
                f"Expected embedding length {dims}, got "
                f"{len(item) if isinstance(item, list) else type(item)}"
            )
        normalized.append([float(value) for value in item])
    return normalized


@lru_cache(maxsize=1)
def _local_model():
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "sentence-transformers is required for EMBEDDING_MODE=local"
        ) from exc
    return SentenceTransformer(_model_name())


def _local_embed(
    texts: Sequence[str],
    *,
    is_query: bool,
) -> list[list[float]]:
    model = _local_model()
    prefixed = [_with_e5_prefix(text, is_query=is_query) for text in texts]
    vectors = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    dims = _dimensions()
    result: list[list[float]] = []
    for row in vectors:
        values = [float(value) for value in row]
        if len(values) != dims:
            raise EmbeddingError(
                f"Local model returned dim={len(values)}, expected {dims}"
            )
        result.append(values)
    return result


def _embed_texts(
    texts: Sequence[str],
    *,
    is_query: bool = False,
) -> tuple[list[list[float]], str]:
    """Embed texts and report which backend produced the vectors."""
    if not texts:
        return [], _mode()
    cleaned = [str(text or "") for text in texts]
    mode = _mode()
    if mode == "lexical":
        dims = _dimensions()
        return [deterministic_embedding(text, dims) for text in cleaned], "lexical"
    if mode == "stub":
        dims = _dimensions()
        return [deterministic_embedding(text, dims) for text in cleaned], "stub"
    if mode == "http":
        try:
            return _http_embed(cleaned, is_query=is_query), "http"
        except EmbeddingError:
            global _http_stub_fallback_logged
            if not _http_stub_fallback_logged:
                logger.warning(
                    "HTTP embedding unavailable; using lexical retrieval "
                    "instead of mixing stub query vectors with stored embeddings"
                )
                _http_stub_fallback_logged = True
            dims = _dimensions()
            return (
                [deterministic_embedding(text, dims) for text in cleaned],
                "http-fallback",
            )
    return _local_embed(cleaned, is_query=is_query), "local"


def embed_texts(
    texts: Sequence[str],
    *,
    is_query: bool = False,
) -> list[list[float]]:
    """Embed one or more texts according to ``EMBEDDING_MODE``."""
    vectors, _backend = _embed_texts(texts, is_query=is_query)
    return vectors


def embed_texts_with_backend(
    texts: Sequence[str],
    *,
    is_query: bool = False,
) -> tuple[list[list[float]], str]:
    """Embed a batch and expose the backend for fail-open semantic routing."""
    return _embed_texts(texts, is_query=is_query)


def embed_text(text: str, *, is_query: bool = False) -> list[float]:
    return embed_texts([text], is_query=is_query)[0]


def embed_query(text: str) -> list[float]:
    return embed_text(text, is_query=True)


def embed_query_with_backend(text: str) -> tuple[list[float], str]:
    key = (_mode(), _model_name(), str(text or ""))
    cached = _query_cache.get(key)
    if cached is not None:
        return cached
    vectors, backend = _embed_texts([text], is_query=True)
    result = (vectors[0], backend)
    if len(_query_cache) >= _QUERY_CACHE_MAX:
        _query_cache.pop(next(iter(_query_cache)))
    _query_cache[key] = result
    return result


def preload_query_embeddings(texts: Sequence[str]) -> None:
    """Batch and cache query vectors for evaluations and bulk previews."""
    keys_and_texts = [
        ((_mode(), _model_name(), str(text or "")), str(text or ""))
        for text in texts
        if str(text or "")
    ]
    missing = [(key, text) for key, text in keys_and_texts if key not in _query_cache]
    if not missing:
        return
    vectors, backend = _embed_texts([text for _key, text in missing], is_query=True)
    for (key, _text), vector in zip(missing, vectors, strict=True):
        if len(_query_cache) >= _QUERY_CACHE_MAX:
            _query_cache.pop(next(iter(_query_cache)))
        _query_cache[key] = (vector, backend)


def embed_passage(text: str) -> list[float]:
    return embed_text(text, is_query=False)


def embedding_backend_info() -> dict[str, str | int]:
    return {
        "mode": _mode(),
        "model": _model_name(),
        "dimensions": _dimensions(),
        "base_url": (os.environ.get("EMBEDDING_BASE_URL") or "").rstrip("/"),
    }


Kind = Literal["query", "passage"]
