"""
Live multi-LLM consensus eval.

Takes pre-computed predictions from THREE models on the same gold set
and runs them through the production consensus algorithm:

  1. Per field of the unified schema, collect every item across models
  2. Embed each item's canonical key with OpenAI text-embedding-3-small
  3. Greedy-cluster by cosine similarity (≥ 0.78)
  4. Per cluster, count distinct providers → confidence
  5. Pick cluster representative (provider preference: anthropic→openai→gemini)
  6. Keep only clusters with ≥ 2/3 providers as the consensus output

Score the consensus output against gold and report:
  - Real Fleiss κ across the three live models
  - Real convergence rate (% items ≥2/3 agree)
  - Real unanimous rate (% items 3/3 agree)
  - Real consensus recall + lift vs mean single-model
  - Per-field disagreement examples

This replaces the SIMULATED consensus benchmark (perturbed gold) with
the live story Arcsine actually pitches.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

# Load env first.
_repo_root = Path(__file__).resolve().parents[3]
_env = _repo_root / ".env"
if _env.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env)
    except ImportError:
        for line in _env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from openai import AsyncOpenAI

from .dataset import EXTRACTION_GOLD
from .metrics.extraction import (
    EXACT_SECTIONS, KEY_FN, SECTIONS, TEXT_FN,
    compare_section, compare_section_fuzzy, PRF,
)


CLUSTER_THRESHOLD = 0.78
EMBED_MODEL = "text-embedding-3-small"


# Field-level canonical-key formatters, mirroring backend/app/pipeline/consensus.py::FIELD_KEY
FIELD_KEY = {
    "diagnoses":   lambda x: f"diagnosis: {x.get('condition','')} {x.get('icd10','')}",
    "medications": lambda x: f"medication: {x.get('name','')} {x.get('dose','')} {x.get('frequency','')}",
    "vitals":      lambda x: f"vital: {x.get('type','')} {x.get('value','')} {x.get('unit','')}",
    "labs":        lambda x: f"lab: {x.get('test','')} {x.get('value','')} {x.get('unit','')}",
    "symptoms":    lambda x: f"symptom: {x.get('description','')}",
    "red_flags":   lambda x: f"red flag: {x.get('finding','')}",
}


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot/(na*nb) if (na and nb) else 0.0


async def _embed(client, texts):
    if not texts:
        return []
    resp = await client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


async def cluster_one_example(
    client, per_model: list[tuple[str, dict]],
) -> tuple[dict, dict]:
    """
    per_model: [(provider_name, prediction_dict), ...]
    Returns (consensus_report, per_field_meta) where per_field_meta is
    {section: [{value_key, providers, votes, confidence}, ...]}
    """
    consensus: dict[str, list[dict]] = {sec: [] for sec in SECTIONS}
    fields_meta: dict[str, list[dict]] = {sec: [] for sec in SECTIONS}
    n_models = len(per_model)

    for sec in SECTIONS:
        # collect (provider, item) pairs
        items: list[tuple[str, dict]] = []
        for provider, pred in per_model:
            for it in (pred.get(sec) or []):
                items.append((provider, it))
        if not items:
            continue

        keys = [FIELD_KEY[sec](it) for _, it in items]
        vecs = await _embed(client, keys)

        # greedy clustering
        clusters: list[dict] = []
        for (provider, it), v in zip(items, vecs):
            placed = False
            for c in clusters:
                if _cosine(v, c["centre"]) >= CLUSTER_THRESHOLD:
                    c["items"].append((provider, it))
                    placed = True
                    break
            if not placed:
                clusters.append({"items": [(provider, it)], "centre": v})

        # consolidate
        for c in clusters:
            providers = sorted({p for p, _ in c["items"]})
            confidence = len(providers) / n_models
            # provider-preference for the canonical representative
            order = ["anthropic", "openai", "gemini"]
            chosen = None
            for pref in order:
                for p, it in c["items"]:
                    if p == pref:
                        chosen = it
                        break
                if chosen is not None:
                    break
            if chosen is None:
                chosen = c["items"][0][1]
            fields_meta[sec].append({
                "value_key":  FIELD_KEY[sec](chosen),
                "providers":  providers,
                "votes":      len(c["items"]),
                "confidence": round(confidence, 3),
            })
            # Consensus rule: keep only clusters with ≥ 2/3 providers
            if confidence >= (2/3 - 1e-6):
                consensus[sec].append(chosen)

    return consensus, fields_meta


def _fleiss_kappa(rows: list[tuple[int, int]], n_raters: int) -> float:
    """Each row = (present_count, absent_count) for one item across raters."""
    if not rows:
        return 0.0
    N = len(rows)
    p_present = sum(r[0] for r in rows) / (N * n_raters)
    p_absent = 1 - p_present
    Pe = p_present**2 + p_absent**2
    Po = sum(
        (p*(p-1) + a*(a-1)) / (n_raters*(n_raters-1))
        for p, a in rows
    ) / N
    if Pe == 1.0:
        return 1.0
    return (Po - Pe) / (1 - Pe)


def _section_recall(gold: dict, pred: dict) -> float:
    tp = fn = 0
    for sec in SECTIONS:
        if sec in EXACT_SECTIONS:
            prf = compare_section(gold.get(sec, []), pred.get(sec, []), KEY_FN[sec])
        else:
            prf = compare_section_fuzzy(gold.get(sec, []), pred.get(sec, []), TEXT_FN[sec])
        tp += prf.tp; fn += prf.fn
    return tp / (tp + fn) if (tp + fn) else 1.0


def _section_f1(gold: dict, pred: dict) -> float:
    tp = fp = fn = 0
    for sec in SECTIONS:
        if sec in EXACT_SECTIONS:
            prf = compare_section(gold.get(sec, []), pred.get(sec, []), KEY_FN[sec])
        else:
            prf = compare_section_fuzzy(gold.get(sec, []), pred.get(sec, []), TEXT_FN[sec])
        tp += prf.tp; fp += prf.fp; fn += prf.fn
    p = tp / (tp + fp) if (tp + fp) else 1.0
    r = tp / (tp + fn) if (tp + fn) else 1.0
    return 2*p*r/(p+r) if (p+r) else 0.0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--m1", required=True, help="Predictions JSON for model 1 (default label: anthropic)")
    ap.add_argument("--m2", required=True, help="Predictions JSON for model 2 (default label: openai)")
    ap.add_argument("--m3", default=None, help="Optional predictions JSON for model 3 (default label: gemini)")
    ap.add_argument("--label1", default="anthropic")
    ap.add_argument("--label2", default="openai")
    ap.add_argument("--label3", default="gemini")
    ap.add_argument("--out", required=True, help="Where to write the live-consensus metrics JSON.")
    args = ap.parse_args()

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise SystemExit("OPENAI_API_KEY missing — needed for embedding-based clustering.")
    client = AsyncOpenAI(api_key=key)

    sources: list[tuple[str, dict]] = []
    sources.append((args.label1, json.loads(Path(args.m1).read_text())))
    sources.append((args.label2, json.loads(Path(args.m2).read_text())))
    if args.m3:
        sources.append((args.label3, json.loads(Path(args.m3).read_text())))

    provider_models = {p: raw.get("model", p) for p, raw in sources}
    n_models = len(sources)
    print(f"Live consensus with {n_models} models: " +
          ", ".join(f"{p}={m}" for p, m in provider_models.items()))

    converged = unanimous = total_fields = 0
    cluster_correct = cluster_total = 0
    per_model_recalls: dict[str, list[float]] = {p: [] for p, _ in sources}
    consensus_recalls: list[float] = []
    consensus_f1s: list[float] = []
    per_example_keys: list[list[list[str]]] = []
    per_example: list[dict] = []

    t0 = time.perf_counter()

    for ex in EXTRACTION_GOLD:
        # Skip examples where any model has no prediction (e.g. image-only).
        per_model: list[tuple[str, dict]] = []
        for provider, raw in sources:
            pred = (raw.get("predictions") or {}).get(ex.id) or {}
            per_model.append((provider, pred))

        if not any(any((p.get(s) or []) for s in SECTIONS) for _, p in per_model):
            # All-empty (vision-only ex06); skip from consensus stats.
            continue

        consensus, fields_meta = await cluster_one_example(client, per_model)

        # Section-key collection for Fleiss kappa.
        per_section_keys_per_model: list[list[str]] = [[] for _ in range(n_models)]
        for sec in SECTIONS:
            for i, (_, pred) in enumerate(per_model):
                for it in (pred.get(sec) or []):
                    per_section_keys_per_model[i].append(f"{sec}::{FIELD_KEY[sec](it)}")
        per_example_keys.append(per_section_keys_per_model)

        # Convergence / unanimous + cluster correctness counts.
        for sec, clusters in fields_meta.items():
            gold_keys_strict = {KEY_FN[sec](g) for g in ex.gold.get(sec, []) if KEY_FN[sec](g)}
            gold_texts = [TEXT_FN[sec](g) for g in ex.gold.get(sec, [])] if sec in TEXT_FN else []
            for c in clusters:
                total_fields += 1
                if c["votes"] >= 2:
                    converged += 1
                if c["confidence"] >= 0.999:
                    unanimous += 1
                cluster_total += 1
                # Cluster representative correctness = matches any gold item
                if sec in EXACT_SECTIONS:
                    # Compare with key_fn against gold
                    found_key = c["value_key"].split(":", 1)[-1].strip()
                    if any(found_key.lower().startswith(gk.lower()[:6]) for gk in gold_keys_strict if gk):
                        cluster_correct += 1
                else:
                    # Use fuzzy text overlap from the value_key against any gold text
                    if any(_token_overlap(c["value_key"], gt) >= 0.4 for gt in gold_texts):
                        cluster_correct += 1

        # Per-model recall vs gold
        for (provider, pred) in per_model:
            per_model_recalls[provider].append(_section_recall(ex.gold, pred))

        # Consensus recall vs gold
        consensus_recalls.append(_section_recall(ex.gold, consensus))
        consensus_f1s.append(_section_f1(ex.gold, consensus))

        per_example.append({
            "id": ex.id,
            "n_fields": sum(len(v) for v in fields_meta.values()),
            "n_converged": sum(1 for clusters in fields_meta.values() for c in clusters if c["votes"] >= 2),
            "consensus_recall": consensus_recalls[-1],
        })

    elapsed = (time.perf_counter() - t0) * 1000
    kappa = _fleiss_kappa(_kappa_rows(per_example_keys, n_models), n_models)
    convergence = converged / total_fields if total_fields else 0.0
    unanim_rate = unanimous / total_fields if total_fields else 0.0
    cluster_corr = cluster_correct / cluster_total if cluster_total else 0.0
    mean_single = {
        p: (sum(rs) / len(rs) if rs else 0.0)
        for p, rs in per_model_recalls.items()
    }
    avg_single = sum(mean_single.values()) / len(mean_single)
    consensus_recall = sum(consensus_recalls) / len(consensus_recalls) if consensus_recalls else 0.0
    consensus_f1 = sum(consensus_f1s) / len(consensus_f1s) if consensus_f1s else 0.0
    lift = consensus_recall - avg_single

    out = {
        "kind": "live",
        "n_examples_scored": len(per_example),
        "models": provider_models,
        "fleiss_kappa":             round(kappa, 4),
        "unanimous_rate":           round(unanim_rate, 4),
        "convergence_rate":         round(convergence, 4),
        "cluster_correctness":      round(cluster_corr, 4),
        "mean_single_recall_per_model": {p: round(v, 4) for p, v in mean_single.items()},
        "mean_single_recall":       round(avg_single, 4),
        "consensus_recall":         round(consensus_recall, 4),
        "consensus_f1":             round(consensus_f1, 4),
        "high_conf_recall_lift":    round(lift, 4),
        "elapsed_ms":               round(elapsed, 1),
        "per_example":              per_example,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nWrote {args.out}")
    print(f"Convergence (≥2/3): {convergence*100:.1f}%   "
          f"Unanimous: {unanim_rate*100:.1f}%   "
          f"Cluster correct: {cluster_corr*100:.1f}%")
    print(f"Mean single recall: {avg_single*100:.1f}%   "
          f"Consensus recall: {consensus_recall*100:.1f}%   "
          f"Lift: {'+' if lift >= 0 else ''}{lift*100:.1f} pts")
    for p, r in mean_single.items():
        print(f"  {p:10s}: recall {r*100:.1f}%")


def _kappa_rows(per_example_keys: list[list[list[str]]], n_raters: int) -> list[tuple[int, int]]:
    rows = []
    for per_model in per_example_keys:
        keys = set()
        for items in per_model:
            keys.update(items)
        for k in keys:
            present = sum(1 for items in per_model if k in items)
            rows.append((present, n_raters - present))
    return rows


def _token_overlap(a: str, b: str) -> float:
    """Same logic as metrics/extraction._overlap but stand-alone."""
    stop = {"the","a","an","of","in","on","at","with","and","or","for","by","to",
            "is","was","were","be","been","has","have","had"}
    qual = {"essential","acute","chronic","suspected","mild","severe","moderate",
            "possible","probable","stage","unilateral","bilateral","right","left",
            "primary","secondary","new","recent","increased","decreased"}
    def toks(s):
        raw = s.lower()
        for ch in "().,;:[]/-":
            raw = raw.replace(ch, " ")
        return {t for t in raw.split() if t and t not in stop and t not in qual}
    ta, tb = toks(a), toks(b)
    if not ta or not tb: return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


if __name__ == "__main__":
    asyncio.run(main())
