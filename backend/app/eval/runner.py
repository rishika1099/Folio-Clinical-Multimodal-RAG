"""
Eval runner — executes every metric module and emits a markdown report.

Usage:
    python -m app.eval.runner                  # run all evals, write EVAL_REPORT.md
    python -m app.eval.runner --live-embed     # use real embedding API
    python -m app.eval.runner --json eval.json # also write machine-readable JSON
"""
from __future__ import annotations
import argparse
import asyncio
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from .dataset import EXTRACTION_GOLD, RAG_QUERIES, PII_CASES, CHAT_PROBES, all_modality_counts
from .metrics.extraction import evaluate_extraction, synthesize_reference_predictions, SECTIONS
from .metrics.rag import evaluate_rag
from .metrics.consensus import evaluate_consensus
from .metrics.pii import evaluate_pii
from .metrics.latency import evaluate_latency
from .metrics.chat import evaluate_chat


def _serialisable(obj):
    if is_dataclass(obj):
        return _serialisable(asdict(obj))
    if isinstance(obj, dict):
        return {k: _serialisable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_serialisable(v) for v in obj]
    return obj


async def run_all(*, live_embed: bool = False, predictions_path: str | None = None) -> dict:
    if predictions_path:
        raw = json.loads(Path(predictions_path).read_text())
        preds = raw.get("predictions") or raw
        prediction_source = {
            "kind": "live",
            "model": raw.get("model"),
            "n": raw.get("n"),
            "total_input_tokens": raw.get("total_input_tokens"),
            "total_output_tokens": raw.get("total_output_tokens"),
            "failed": raw.get("failed") or [],
        }
    else:
        preds = synthesize_reference_predictions()
        prediction_source = {"kind": "synthetic"}
    extraction = evaluate_extraction(preds)
    rag = await evaluate_rag(use_live_embeddings=live_embed)
    consensus = evaluate_consensus()
    pii = evaluate_pii()
    latency = await evaluate_latency()
    chat = evaluate_chat()

    return {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "n_extraction_examples": len(EXTRACTION_GOLD),
            "n_rag_queries": len(RAG_QUERIES),
            "n_pii_cases": len(PII_CASES),
            "n_chat_probes": len(CHAT_PROBES),
            "modality_counts": all_modality_counts(),
            "live_embed": live_embed,
            "prediction_source": prediction_source,
        },
        "extraction": _serialisable(extraction),
        "rag": _serialisable(rag),
        "consensus": _serialisable(consensus),
        "pii": _serialisable(pii),
        "latency": _serialisable(latency),
        "chat": _serialisable(chat),
    }


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_markdown(results: dict, path: Path) -> None:
    e = results["extraction"]
    r = results["rag"]
    c = results["consensus"]
    p = results["pii"]
    l = results["latency"]
    ch = results["chat"]
    meta = results["meta"]

    lines: list[str] = []
    out = lines.append

    out("# Folio — Evaluation Report")
    out("")
    out(f"_Generated {meta['generated_at']} · {meta['n_extraction_examples']} extraction examples "
        f"· {meta['n_rag_queries']} RAG queries · {meta['n_pii_cases']} PII cases · "
        f"{meta['n_chat_probes']} chat probes_")
    out("")
    src = meta.get("prediction_source", {})
    if src.get("kind") == "live":
        out(f"**Extraction predictions: LIVE** — `{src.get('model','?')}` on {src.get('n','?')} examples "
            f"({src.get('total_input_tokens',0):,} input + {src.get('total_output_tokens',0):,} output tokens).")
    else:
        out("**Extraction predictions: synthetic** (gold-with-seeded-errors). "
            "Run `live_extract.py` and pass `--predictions <path>` for real model numbers.")
    out("")
    out("All metrics are reproducible — `python -m app.eval.runner` regenerates this file.")
    out("")

    out("## Headline numbers")
    out("")
    out("| Area | Metric | Value |")
    out("|---|---|---|")
    out(f"| Extraction | Micro-F1 (all sections) | **{pct(e['micro_f1'])}** |")
    out(f"| Extraction | Macro-F1 (mean across sections) | **{pct(e['macro_f1'])}** |")
    out(f"| Extraction | Schema validity | {pct(e['schema_valid'])} |")
    out(f"| Extraction | Hallucination rate | {pct(e['hallucination'])} |")
    out(f"| Extraction | Coverage of gold items | {pct(e['coverage'])} |")
    out(f"| RAG | Recall@1 | **{pct(r['recall_at']['1'] if isinstance(list(r['recall_at'].keys())[0], str) else r['recall_at'][1])}** |")
    out(f"| RAG | Recall@5 | {pct(_rk(r, 5))} |")
    out(f"| RAG | MRR | {r['mrr']:.3f} |")
    out(f"| RAG | NDCG@10 | {r['ndcg10']:.3f} |")
    out(f"| Consensus | Unanimous agreement (3/3) | {pct(c['unanimous_rate'])} |")
    out(f"| Consensus | Convergence (≥2/3) | {pct(c['convergence_rate'])} |")
    out(f"| Consensus | Cluster representative correctness | {pct(c['cluster_correctness'])} |")
    out(f"| Consensus | Recall lift over single-model average | +{pct(c['high_conf_recall_lift'])} |")
    out(f"| PII | Scrub recall | **{pct(p['scrub_recall'])}** |")
    out(f"| PII | Content preservation | {pct(p['content_preservation'])} |")
    out(f"| Chat | Answer correctness | {pct(ch['answer_correctness'])} |")
    out(f"| Chat | Citation correctness | {pct(ch['citation_correctness'])} |")
    out(f"| Chat | Red-flag detection recall | {pct(ch['red_flag_recall'])} |")
    out(f"| Chat | Hallucination guard | {pct(ch['hallucination_guard'])} |")
    out(f"| Latency | PII scrub p50 / p95 | {l['pii_scrub']['samples'] and _p(l['pii_scrub'], 0.5)} ms / {l['pii_scrub'] and _p(l['pii_scrub'], 0.95)} ms |")
    out(f"| Latency | Hash-embed p50 (per doc) | {_p(l['hash_embed'], 0.5)} ms |")
    out(f"| Latency | Cosine search p50 over corpus | {_p(l['cosine_search'], 0.5)} ms |")
    out("")

    # ---- extraction ------------------------------------------------------
    out("## 1. Extraction quality")
    out("")
    out("Per-section precision / recall / F1, aggregated across the gold "
        "corpus. Items are matched on canonical keys (condition name, "
        "drug name, vital type, lab test name, first words of symptom / "
        "red-flag description) so formatting variants count as a match.")
    out("")
    out("| Section | TP | FP | FN | Precision | Recall | F1 |")
    out("|---|---:|---:|---:|---:|---:|---:|")
    for sec in SECTIONS:
        s = e["per_section"][sec]
        prec = s["tp"] / (s["tp"] + s["fp"]) if (s["tp"] + s["fp"]) else 1.0
        rec = s["tp"] / (s["tp"] + s["fn"]) if (s["tp"] + s["fn"]) else 1.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        out(f"| {sec} | {s['tp']} | {s['fp']} | {s['fn']} | {pct(prec)} | {pct(rec)} | **{pct(f1)}** |")
    out("")

    out("### By modality")
    out("")
    out("| Modality | N | Macro-F1 |")
    out("|---|---:|---:|")
    for mod, stats in e["by_modality"].items():
        out(f"| {mod} | {stats['n']} | {pct(stats['macro_f1'])} |")
    out("")

    out("### By difficulty")
    out("")
    out("| Tag | N | Macro-F1 |")
    out("|---|---:|---:|")
    for d, stats in e["by_difficulty"].items():
        out(f"| {d} | {stats['n']} | {pct(stats['macro_f1'])} |")
    out("")

    # ---- RAG -------------------------------------------------------------
    out("## 2. RAG retrieval")
    out("")
    out("Top-k retrieval over the gold corpus for each canonical query. "
        "Embeddings are " + ("**live (OpenAI text-embedding-3-small)**" if meta["live_embed"]
                              else "deterministic hash-bag pseudo-embeddings (live API replaces these in production)") + ".")
    out("")
    out("| Metric | Value |")
    out("|---|---:|")
    out(f"| Recall@1 | {pct(_rk(r, 1))} |")
    out(f"| Recall@3 | {pct(_rk(r, 3))} |")
    out(f"| Recall@5 | {pct(_rk(r, 5))} |")
    out(f"| Recall@10 | {pct(_rk(r, 10))} |")
    out(f"| MRR | {r['mrr']:.3f} |")
    out(f"| NDCG@10 | {r['ndcg10']:.3f} |")
    out(f"| Mean embed time per query | {r['mean_embed_ms']:.2f} ms |")
    out(f"| Mean cosine search time per query | {r['mean_search_ms']:.3f} ms |")
    out("")

    out("### Per-query top-5")
    out("")
    out("| Query | First-hit rank | Top-5 returned |")
    out("|---|---:|---|")
    for q in r["per_query"]:
        rank = q["first_hit_rank"] or "—"
        top = ", ".join(t.split("_")[0] for t in q["top5"][:5])
        out(f"| {q['query']} | {rank} | `{top}` |")
    out("")

    # ---- Consensus -------------------------------------------------------
    out("## 3. Multi-LLM consensus")
    out("")
    out("Three simulated models (Anthropic / OpenAI / Gemini perturbations of gold) "
        "are passed through the same field-level clustering + voting pipeline used "
        "in production. This benchmarks the *consensus algorithm*, not the underlying "
        "models — running against live models requires API budget.")
    out("")
    out("| Metric | Value |")
    out("|---|---:|")
    out(f"| Unanimous agreement (3/3 models had item) | {pct(c['unanimous_rate'])} |")
    out(f"| Convergence (≥2/3 had item — what consensus keeps) | {pct(c['convergence_rate'])} |")
    out(f"| Cluster representative matches gold | {pct(c['cluster_correctness'])} |")
    out(f"| Mean single-model recall (across 3 models) | {pct(c['mean_single_recall'])} |")
    out(f"| Consensus recall | **{pct(c['consensus_recall'])}** |")
    out(f"| Lift vs single-model average | +{pct(c['high_conf_recall_lift'])} |")
    out(f"| Fleiss' κ (raw, for reference) | {c['fleiss_kappa']:.3f} |")
    out(f"| Input-token cost ratio (consensus vs single) | {c['cost_ratio']:.1f}× |")
    out("")
    out("> **Note on Fleiss κ.** For this synthetic perturbation scheme "
        "(model 0 drops last, model 1 drops first, model 2 perfect) the "
        "κ can read slightly negative because the disagreements happen "
        "systematically rather than at random — the formula penalises "
        "structured disagreement. The actionable numbers are convergence "
        "rate and consensus recall lift, both shown above.")
    out("")

    # ---- PII -------------------------------------------------------------
    out("## 4. PII scrubbing")
    out("")
    out(f"Tested across **{p['n_cases']}** canonical PII cases covering SSN, MRN, "
        "email, phone, DOB, plus a clean-input control. Coverage broken out by class:")
    out("")
    out("| Class | Cases | Recall |")
    out("|---|---:|---:|")
    for cls, c2 in p["by_class"].items():
        out(f"| {cls} | {int(c2['total'])} | {pct(c2['recall'])} |")
    out("")
    out(f"- **Total scrub recall**: {pct(p['scrub_recall'])}")
    out(f"- **Content preservation** (clinical info kept intact): {pct(p['content_preservation'])}")
    if p["failures"]:
        out("")
        out("### Failures")
        out("")
        for f in p["failures"]:
            if "missed" in f:
                out(f"- ❌ missed `{f['missed']}` ({f['class']}) in: _{f['case']}…_")
            elif "destroyed" in f:
                out(f"- ⚠️ destroyed clinical text `{f['destroyed']}` in: _{f['case']}…_")
    out("")

    # ---- Latency ---------------------------------------------------------
    out("## 5. Latency")
    out("")
    out(f"Sampled n={l['pii_scrub']['samples'] and len(l['pii_scrub']['samples'])} runs per stage on local hardware.")
    out("")
    out("| Stage | Mean | p50 | p95 | p99 |")
    out("|---|---:|---:|---:|---:|")
    for label, key in [("PII scrub", "pii_scrub"),
                        ("Hash embed (per doc)", "hash_embed"),
                        ("Cosine search (full corpus)", "cosine_search")]:
        d = l[key]
        out(f"| {label} | {d['samples'] and (sum(d['samples'])/len(d['samples'])):.3f} ms | "
             f"{_p(d, 0.5)} ms | {_p(d, 0.95)} ms | {_p(d, 0.99)} ms |")
    out("")

    # ---- Chat -------------------------------------------------------------
    out("## 6. Chat groundedness")
    out("")
    out("Probes the chat path with canned questions whose factually correct answers "
        "live in the gold corpus. Synthesised reference replies stand in when no "
        "Anthropic key is configured; live runs would substitute real model outputs.")
    out("")
    out("| Metric | Value |")
    out("|---|---:|")
    out(f"| Answer correctness (key term present) | {pct(ch['answer_correctness'])} |")
    out(f"| Citation correctness (right reports cited) | {pct(ch['citation_correctness'])} |")
    out(f"| Red-flag escalation recall | {pct(ch['red_flag_recall'])} |")
    out(f"| Hallucination guard (forbidden strings absent) | {pct(ch['hallucination_guard'])} |")
    out("")

    out("---")
    out("")
    out("**Reproducing this report**")
    out("")
    out("```bash")
    out("docker compose exec backend python -m app.eval.runner")
    out("# Add --live-embed to use the real OpenAI embedding endpoint")
    out("# Add --json out.json to also write machine-readable results")
    out("```")
    out("")
    out("Synthetic eval data is hand-authored in `backend/app/eval/dataset.py` and "
        "deliberately covers easy / medium / hard cases across all four input "
        "modalities, plus emergency red-flag scenarios.")

    path.write_text("\n".join(lines))


def _rk(r: dict, k: int) -> float:
    # recall_at is keyed by ints originally; dataclass serialisation may
    # have stringified the keys. Tolerate either.
    rec = r["recall_at"]
    if k in rec:
        return rec[k]
    return rec.get(str(k), 0.0)


def _p(d: dict, q: float) -> str:
    s = d.get("samples") or []
    if not s:
        return "0.000"
    ss = sorted(s)
    idx = max(0, min(len(ss) - 1, int(q * (len(ss) - 1))))
    return f"{ss[idx]:.3f}"


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-embed", action="store_true",
                    help="Use the real OpenAI embedding endpoint for RAG eval.")
    ap.add_argument("--predictions", default=None,
                    help="Path to a JSON file of real-model predictions from live_extract.py. "
                         "When omitted, uses deterministic synthetic predictions.")
    ap.add_argument("--json", default=None, help="Also write machine-readable JSON to this path.")
    ap.add_argument("--out", default=None, help="Markdown output path (default: repo root EVAL_REPORT.md).")
    args = ap.parse_args()

    results = await run_all(live_embed=args.live_embed, predictions_path=args.predictions)

    out_md = Path(args.out) if args.out else Path(__file__).resolve().parents[3] / "EVAL_REPORT.md"
    write_markdown(results, out_md)
    print(f"Wrote {out_md}")

    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=str))
        print(f"Wrote {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
