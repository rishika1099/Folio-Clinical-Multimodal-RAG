"""
RAG retrieval metrics computed over a fixed corpus + query set.

For each gold query we know the set of relevant report ids. We embed
each query, run cosine similarity against the corpus of report digests,
and rank by score. Standard IR metrics fall out:

  - Recall@k for k ∈ {1, 3, 5, 10}
  - MRR (Mean Reciprocal Rank of the first relevant hit)
  - NDCG@10 (Normalised Discounted Cumulative Gain)
  - Mean embed time / search time per query
"""
from __future__ import annotations
import math
import time
from dataclasses import dataclass

from ..dataset import EXTRACTION_GOLD, RAG_QUERIES, GoldExample


def cosine(a: list[float], b: list[float]) -> float:
    """Pure-stdlib cosine — duplicated from rag.embeddings to keep the
    eval module importable without redis/openai deps. The production
    implementation is identical."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    return dot / (math.sqrt(na) * math.sqrt(nb)) if (na and nb) else 0.0


async def embed_many(texts):
    """Stub — only used in the --live-embed branch. The real impl lives
    in rag.embeddings and is imported lazily when needed."""
    from ...rag.embeddings import embed_many as _real
    return await _real(texts)


async def embed_one(text):
    from ...rag.embeddings import embed_one as _real
    return await _real(text)


def _digest(ex: GoldExample) -> str:
    """Build the same digest the real RAG store would have indexed."""
    g = ex.gold
    parts = [f"Report ({ex.modality}). {ex.input[:240]}"]
    for d in g.get("diagnoses", []):
        parts.append(f"Diagnosis: {d.get('condition','')}.")
    for m in g.get("medications", []):
        parts.append(f"Medication: {m.get('name','')} {m.get('dose','')} {m.get('frequency','')}.")
    for v in g.get("vitals", []):
        parts.append(f"Vital: {v.get('type','').upper()} {v.get('value','')} {v.get('unit','')}.")
    for l in g.get("labs", []):
        parts.append(f"Lab: {l.get('test','')} {l.get('value','')} {l.get('unit','')}.")
    for s in g.get("symptoms", []):
        parts.append(f"Symptom: {s.get('description','')}.")
    for f in g.get("red_flags", []):
        parts.append(f"Red flag: {f.get('finding','')}.")
    return " ".join(parts)


@dataclass
class RagResult:
    n_queries: int
    corpus_size: int
    recall_at: dict[int, float]
    mrr: float
    ndcg10: float
    mean_embed_ms: float
    mean_search_ms: float
    per_query: list[dict]


def _ndcg(relevant: set[str], ranked: list[str], k: int = 10) -> float:
    dcg = 0.0
    for i, rid in enumerate(ranked[:k]):
        if rid in relevant:
            dcg += 1.0 / math.log2(i + 2)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(len(relevant), k)))
    return dcg / ideal if ideal else 0.0


async def evaluate_rag(*, use_live_embeddings: bool = False) -> RagResult:
    """
    use_live_embeddings: if True, calls the real embedding API. If False,
    uses a deterministic hash-based pseudo-embedding so the framework
    runs without network. Hash-based scores are weaker but produce
    well-defined ranks for unit-testing the harness.
    """
    if use_live_embeddings:
        # Real embeddings via the project's embed_many helper.
        corpus_digests = [_digest(e) for e in EXTRACTION_GOLD]
        corpus_vecs = await embed_many(corpus_digests)
        async def embed_q(q: str):
            return await embed_one(q)
    else:
        corpus_vecs = [_hash_embed(_digest(e)) for e in EXTRACTION_GOLD]
        async def embed_q(q: str):
            return _hash_embed(q)

    ks = [1, 3, 5, 10]
    recall_hits = {k: 0 for k in ks}
    rr_sum = 0.0
    ndcg_sum = 0.0
    embed_ms: list[float] = []
    search_ms: list[float] = []
    per_query: list[dict] = []

    corpus_ids = [e.id for e in EXTRACTION_GOLD]

    for q in RAG_QUERIES:
        t0 = time.perf_counter()
        qv = await embed_q(q.query)
        embed_ms.append((time.perf_counter() - t0) * 1000)

        t1 = time.perf_counter()
        scored = sorted(
            ((cosine(qv, cv), cid) for cv, cid in zip(corpus_vecs, corpus_ids)),
            key=lambda x: x[0], reverse=True,
        )
        search_ms.append((time.perf_counter() - t1) * 1000)

        ranked_ids = [cid for _, cid in scored]
        first_hit_rank = next(
            (i + 1 for i, cid in enumerate(ranked_ids) if cid in q.relevant_ids),
            None,
        )
        rr_sum += (1.0 / first_hit_rank) if first_hit_rank else 0.0

        for k in ks:
            if any(cid in q.relevant_ids for cid in ranked_ids[:k]):
                recall_hits[k] += 1

        ndcg_sum += _ndcg(q.relevant_ids, ranked_ids, 10)

        per_query.append({
            "query": q.query,
            "relevant": sorted(q.relevant_ids),
            "top5": ranked_ids[:5],
            "first_hit_rank": first_hit_rank,
        })

    n = len(RAG_QUERIES)
    return RagResult(
        n_queries=n,
        corpus_size=len(EXTRACTION_GOLD),
        recall_at={k: recall_hits[k] / n for k in ks},
        mrr=rr_sum / n if n else 0.0,
        ndcg10=ndcg_sum / n if n else 0.0,
        mean_embed_ms=sum(embed_ms) / len(embed_ms) if embed_ms else 0.0,
        mean_search_ms=sum(search_ms) / len(search_ms) if search_ms else 0.0,
        per_query=per_query,
    )


def _hash_embed(text: str, dim: int = 1536) -> list[float]:
    """
    Deterministic pseudo-embedding via token-hash bag-of-words.
    Each token contributes a sparse +1 in a hashed position; final
    vector is L2-normalised. Not as good as real embeddings, but
    enough that semantically related strings cluster.
    """
    import hashlib
    vec = [0.0] * dim
    tokens = [t for t in text.lower().split() if len(t) > 2]
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
        # secondary hash to spread the mass
        vec[(h >> 13) % dim] += 0.5
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]
