"""CPU embedding HTTP service for multilingual-e5-large (1024-d)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_NAME = (os.environ.get("EMBEDDING_MODEL") or "intfloat/multilingual-e5-large").strip()
try:
    DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS") or "1024")
except ValueError:
    DIMENSIONS = 1024

_model: SentenceTransformer | None = None


def _with_e5_prefix(text: str, *, is_query: bool) -> str:
    stripped = (text or "").strip()
    lowered = stripped.casefold()
    if lowered.startswith("query:") or lowered.startswith("passage:"):
        return stripped
    prefix = "query: " if is_query else "passage: "
    return f"{prefix}{stripped}"


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_model()
    yield


app = FastAPI(title="Sufler embeddings", lifespan=lifespan)


class EmbedRequest(BaseModel):
    texts: list[str] = Field(default_factory=list)
    is_query: bool = False
    model: str | None = None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "ok": True,
        "model": MODEL_NAME,
        "dimensions": DIMENSIONS,
        "ready": _model is not None,
    }


@app.post("/embed")
def embed(request: EmbedRequest) -> dict[str, Any]:
    if request.model and request.model != MODEL_NAME:
        raise HTTPException(status_code=400, detail="unsupported_model")
    model = get_model()
    prefixed = [_with_e5_prefix(text, is_query=request.is_query) for text in request.texts]
    raw = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    embeddings: list[list[float]] = []
    for row in raw:
        values = [float(value) for value in row]
        if len(values) != DIMENSIONS:
            raise HTTPException(
                status_code=500,
                detail=f"expected_dim_{DIMENSIONS}_got_{len(values)}",
            )
        embeddings.append(values)
    return {"embeddings": embeddings, "model": MODEL_NAME}
