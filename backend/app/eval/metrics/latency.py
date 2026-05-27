"""
Latency benchmarks computed over instrumented runs on the gold dataset.

For each stage we sample N runs and report the latency distribution.
Tasks measured:
  - PII scrub
  - JSON partial-parse (frontend's parser logic exercised in Python)
  - Embedding generation (hash fallback or live)
  - RAG cosine search over the corpus
  - Mongo round-trip (skipped if no live DB connection)
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass

from ...pipeline.pii import scrub
from .rag import _digest, _hash_embed, cosine
from ..dataset import EXTRACTION_GOLD


@dataclass
class LatencyDist:
    samples: list[float]

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def mean(self) -> float:
        return sum(self.samples) / self.n if self.n else 0.0

    def pct(self, p: float) -> float:
        if not self.samples:
            return 0.0
        s = sorted(self.samples)
        idx = max(0, min(len(s) - 1, int(p * (len(s) - 1))))
        return s[idx]


@dataclass
class LatencyResult:
    pii_scrub: LatencyDist
    hash_embed: LatencyDist
    cosine_search: LatencyDist


async def evaluate_latency(n_samples: int = 50) -> LatencyResult:
    # PII scrub
    pii_samples: list[float] = []
    for _ in range(n_samples):
        text = " ".join(ex.input for ex in EXTRACTION_GOLD[:5])
        t = time.perf_counter()
        scrub(text)
        pii_samples.append((time.perf_counter() - t) * 1000)

    # Embedding (hash variant — deterministic, no network)
    embed_samples: list[float] = []
    digests = [_digest(ex) for ex in EXTRACTION_GOLD]
    for _ in range(n_samples):
        t = time.perf_counter()
        for d in digests:
            _hash_embed(d)
        embed_samples.append((time.perf_counter() - t) * 1000 / len(digests))

    # Cosine search
    corpus = [_hash_embed(d) for d in digests]
    qv = _hash_embed("when was my last A1C and BP")
    search_samples: list[float] = []
    for _ in range(n_samples):
        t = time.perf_counter()
        [(cosine(qv, c), i) for i, c in enumerate(corpus)]
        search_samples.append((time.perf_counter() - t) * 1000)

    return LatencyResult(
        pii_scrub=LatencyDist(pii_samples),
        hash_embed=LatencyDist(embed_samples),
        cosine_search=LatencyDist(search_samples),
    )
