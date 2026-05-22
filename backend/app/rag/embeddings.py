"""
Embedding service. Uses OpenAI text-embedding-3-small (1536-d, $0.02/M tokens
— cheap enough to embed every report on ingest plus every chat query).

Cached in Redis so re-embedding identical inputs is free. Falls back to
Gemini's text-embedding-004 if OpenAI is unavailable.
"""
import asyncio
import hashlib
import json
import math
from typing import Sequence

from ..cache import get_redis
from ..config import settings
from ..models.router import _gemini_client, _openai_client


EMBED_MODEL_OPENAI = "text-embedding-3-small"   # 1536 dims
EMBED_MODEL_GEMINI = "text-embedding-004"       # 768 dims
EMBED_DIM = 1536


def _key(text: str, model: str) -> str:
    h = hashlib.sha256(f"{model}::{text}".encode()).hexdigest()[:32]
    return f"folio:emb:{h}"


async def embed_one(text: str) -> list[float]:
    """Embed a single string. Caches by sha256(text + model)."""
    text = (text or "").strip()
    if not text:
        return [0.0] * EMBED_DIM
    cache = get_redis()
    cached = None
    try:
        cached = await cache.get(_key(text, EMBED_MODEL_OPENAI))
    except Exception:
        pass
    if cached:
        return json.loads(cached)

    vec = await _embed_openai(text) if settings.openai_api_key else await _embed_gemini(text)
    try:
        await cache.set(_key(text, EMBED_MODEL_OPENAI), json.dumps(vec), ex=60 * 60 * 24 * 30)
    except Exception:
        pass
    return vec


async def embed_many(texts: Sequence[str]) -> list[list[float]]:
    """Batch embed. Uses provider batching when possible."""
    texts = [t.strip() for t in texts]
    if not any(texts):
        return [[0.0] * EMBED_DIM for _ in texts]
    if settings.openai_api_key:
        client = _openai_client()
        resp = await client.embeddings.create(model=EMBED_MODEL_OPENAI, input=list(texts))
        return [d.embedding for d in resp.data]
    # Gemini doesn't batch the same way; fall back to parallel single-calls.
    return await asyncio.gather(*(embed_one(t) for t in texts))


async def _embed_openai(text: str) -> list[float]:
    client = _openai_client()
    resp = await client.embeddings.create(model=EMBED_MODEL_OPENAI, input=text)
    return resp.data[0].embedding


async def _embed_gemini(text: str) -> list[float]:
    genai = _gemini_client()
    if genai is None:
        return [0.0] * EMBED_DIM
    loop = asyncio.get_event_loop()
    def _do():
        out = genai.embed_content(model=f"models/{EMBED_MODEL_GEMINI}", content=text)
        # Gemini returns 768-d; pad/truncate to EMBED_DIM so storage stays uniform.
        v = list(out["embedding"])
        if len(v) < EMBED_DIM:
            v = v + [0.0] * (EMBED_DIM - len(v))
        return v[:EMBED_DIM]
    return await loop.run_in_executor(None, _do)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0; na = 0.0; nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0 or nb == 0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))
