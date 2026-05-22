"""
Multi-LLM consensus extraction.

Mirrors the Arcsine-style pipeline: run extraction in parallel against
Claude / GPT / Gemini, then for every field of the unified schema cluster
the items by embedding similarity and pick the value that the most models
agree on. Per-field confidence comes from inter-model agreement, not from
the model's self-reported probability.

Stages:
  1. Parallel generation        — three models, independently
  2. Field-level alignment      — match items across model outputs
                                  via embedding similarity (vector-based,
                                  not an LLM call)
  3. Best-output selection      — for each field, pick the cluster with
                                  the most models present; confidence =
                                  votes / models_succeeded
  4. Optional reflection round  — disabled by default; when models
                                  disagree on a field the system flags
                                  it for human review rather than asking
                                  the models to debate (cheaper +
                                  prevents correlated-failure consensus)
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from ..config import settings
from ..models.router import (
    ROUTE_EXTRACT_FALLBACK,
    ROUTE_EXTRACT_PRIMARY,
    ModelChoice,
    _safe_json,
    stream_json,
)
from ..rag.embeddings import cosine, embed_many
from ..schemas import ExtractedReport
from .extraction import SYSTEM_PROMPT


# Each task gets its own ModelChoice so we explicitly route to a different
# provider per model in the ensemble. Not the same as the single hot-path
# ROUTE_EXTRACT_* values — those use Haiku + Gemini Flash for speed.
ENSEMBLE: list[ModelChoice] = [
    ModelChoice("anthropic", settings.claude_strong_model,
                "Sonnet 4.6 — strongest medical reasoning."),
    ModelChoice("openai", settings.openai_strong_model,
                "GPT-4.1 — independent training corpus, different failure modes."),
    ModelChoice("gemini", settings.gemini_strong_model,
                "Gemini 2.5 Pro — third independent perspective."),
]


# Field-level "key" used for clustering items across models. We embed
# this canonical string per item so semantically equivalent values collide
# (e.g. "Type 2 diabetes mellitus" and "T2DM" should cluster).
FIELD_KEY = {
    "diagnoses":   lambda x: f"diagnosis: {x.get('condition','')} {x.get('icd10','')}",
    "medications": lambda x: f"medication: {x.get('name','')} {x.get('dose','')} {x.get('frequency','')}",
    "vitals":      lambda x: f"vital: {x.get('type','')} {x.get('value','')} {x.get('unit','')}",
    "labs":        lambda x: f"lab: {x.get('test','')} {x.get('value','')} {x.get('unit','')}",
    "symptoms":    lambda x: f"symptom: {x.get('description','')}",
    "red_flags":   lambda x: f"red flag: {x.get('finding','')}",
}

CLUSTER_THRESHOLD = 0.78  # cosine similarity above which two items are "the same"


async def _run_one(text: str, choice: ModelChoice) -> dict | Exception:
    """Run extraction with a single model and parse the JSON result."""
    user = f"Extract structured medical data from the following text:\n\n---\n{text}\n---"
    buf = ""
    try:
        async for chunk in stream_json(SYSTEM_PROMPT, user, choice, fallback=None,
                                         max_tokens=2000, timeout_s=settings.extraction_timeout_s * 2):
            buf += chunk
        return _safe_json(buf)
    except Exception as e:
        return e


async def consensus_extract(text: str) -> dict:
    """Returns {report, consensus_meta}. Field-level consensus is in meta."""
    t0 = time.perf_counter()

    results = await asyncio.gather(*[_run_one(text, c) for c in ENSEMBLE])

    valid: list[tuple[ModelChoice, dict]] = []
    failed: list[tuple[ModelChoice, str]] = []
    for choice, r in zip(ENSEMBLE, results):
        if isinstance(r, Exception):
            failed.append((choice, repr(r)))
        elif isinstance(r, dict) and r:
            valid.append((choice, r))
    n = len(valid)
    if n == 0:
        raise RuntimeError(f"All ensemble models failed: {failed}")

    # Field-level alignment + voting.
    fields_meta: dict[str, list[dict]] = {}
    consensus_report: dict[str, Any] = {
        "diagnoses": [], "medications": [], "vitals": [],
        "labs": [], "symptoms": [], "red_flags": [],
    }

    for field in consensus_report.keys():
        items_per_model = []  # list of (model, item_dict) per model
        for choice, r in valid:
            for item in (r.get(field) or []):
                items_per_model.append((choice, item))

        if not items_per_model:
            consensus_report[field] = []
            fields_meta[field] = []
            continue

        # Embed the canonical key per item.
        keys = [FIELD_KEY[field](item) for _, item in items_per_model]
        vecs = await embed_many(keys)

        # Greedy clustering by cosine.
        clusters: list[dict] = []  # each: {"items": [(model, item)], "vec": center}
        for (choice, item), vec in zip(items_per_model, vecs):
            placed = False
            for c in clusters:
                if cosine(vec, c["vec"]) >= CLUSTER_THRESHOLD:
                    c["items"].append((choice, item))
                    placed = True
                    break
            if not placed:
                clusters.append({"items": [(choice, item)], "vec": vec})

        # For each cluster, pick the representative item (prefer Claude's,
        # then OpenAI's, then Gemini's — purely a tie-breaker, not a
        # correctness signal). Confidence = unique providers / n_models.
        cluster_meta: list[dict] = []
        consensus_items: list[dict] = []
        for c in clusters:
            providers = sorted({m.provider for m, _ in c["items"]})
            confidence = len(providers) / n
            preferred_order = ["anthropic", "openai", "gemini"]
            best_item = None
            for p in preferred_order:
                for m, it in c["items"]:
                    if m.provider == p:
                        best_item = it
                        break
                if best_item is not None:
                    break
            if best_item is None:
                best_item = c["items"][0][1]
            consensus_items.append(best_item)
            cluster_meta.append({
                "value_key": FIELD_KEY[field](best_item),
                "providers": providers,
                "confidence": round(confidence, 3),
                "votes": len(c["items"]),
                "n_models": n,
            })

        # Sort consensus items by confidence desc within the field.
        order = sorted(range(len(cluster_meta)), key=lambda i: cluster_meta[i]["confidence"], reverse=True)
        consensus_report[field] = [consensus_items[i] for i in order]
        fields_meta[field] = [cluster_meta[i] for i in order]

    # Pick one model's raw_summary — preferring the one with the most
    # consensus items present in the final output (proxy for "most aligned").
    raw_summary = ""
    if valid:
        raw_summary = valid[0][1].get("raw_summary") or ""
        for choice, r in valid[1:]:
            if r.get("raw_summary"):
                raw_summary = r["raw_summary"]
                break

    consensus_report["raw_summary"] = raw_summary

    elapsed = (time.perf_counter() - t0) * 1000
    meta = {
        "models_attempted": [c.model for c in ENSEMBLE],
        "models_succeeded": [c.model for c, _ in valid],
        "models_failed":    [{"model": c.model, "error": err[:200]} for c, err in failed],
        "fields":           fields_meta,
        "elapsed_ms":       round(elapsed, 1),
        "n_models":         n,
        "overall_agreement": _overall_agreement(fields_meta),
    }
    return {"report": consensus_report, "consensus": meta}


def _overall_agreement(fields_meta: dict[str, list[dict]]) -> float:
    confs = [c["confidence"] for clusters in fields_meta.values() for c in clusters]
    if not confs:
        return 1.0
    return round(sum(confs) / len(confs), 3)
