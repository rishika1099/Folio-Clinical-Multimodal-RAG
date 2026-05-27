"""
Head-to-head runner. Loads multiple prediction JSONs (one per model),
scores them against the same gold set, and emits a combined report
the frontend Benchmarks page renders with a model-toggle.

Shape of the output JSON:

    {
      "meta": { ... corpus counts ... },
      "models": {                          # one entry per predictions file
        "haiku":  { "extraction": {...}, "source": {...} },
        "sonnet": { "extraction": {...}, "source": {...} }
      },
      "rag":       { ... },                # model-independent
      "consensus": { ... },
      "pii":       { ... },
      "latency":   { ... },
      "chat":      { ... }
    }

Run:
    python -m app.eval.compare \\
        --haiku  app/eval/predictions_haiku.json \\
        --sonnet app/eval/predictions_sonnet.json \\
        --out ../frontend/public/eval-latest.json \\
        --live-embed
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

# Load .env from repo root before any settings import.
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

from .dataset import EXTRACTION_GOLD, RAG_QUERIES, PII_CASES, CHAT_PROBES, all_modality_counts
from .metrics.extraction import evaluate_extraction
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


def _load(path: str) -> dict:
    raw = json.loads(Path(path).read_text())
    return raw


def _score_model(label: str, raw: dict) -> dict:
    preds = raw.get("predictions") or raw
    extraction = evaluate_extraction(preds)
    return {
        "label": label,
        "extraction": _serialisable(extraction),
        "source": {
            "model": raw.get("model"),
            "n": raw.get("n"),
            "total_input_tokens": raw.get("total_input_tokens"),
            "total_output_tokens": raw.get("total_output_tokens"),
            "failed": raw.get("failed") or [],
        },
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--haiku",  required=True, help="Predictions JSON for the fast model.")
    ap.add_argument("--sonnet", required=True, help="Predictions JSON for the strong model.")
    ap.add_argument("--out",    required=True, help="Where to write the combined report JSON.")
    ap.add_argument("--live-embed", action="store_true")
    args = ap.parse_args()

    haiku_raw = _load(args.haiku)
    sonnet_raw = _load(args.sonnet)

    rag = await evaluate_rag(use_live_embeddings=args.live_embed)
    consensus = evaluate_consensus()
    pii = evaluate_pii()
    latency = await evaluate_latency()
    chat = evaluate_chat()

    out = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "n_extraction_examples": len(EXTRACTION_GOLD),
            "n_rag_queries": len(RAG_QUERIES),
            "n_pii_cases": len(PII_CASES),
            "n_chat_probes": len(CHAT_PROBES),
            "modality_counts": all_modality_counts(),
            "live_embed": args.live_embed,
            "comparison": True,
        },
        "models": {
            "haiku":  _score_model("Claude Haiku 4.5", haiku_raw),
            "sonnet": _score_model("Claude Sonnet 4.5", sonnet_raw),
        },
        "rag": _serialisable(rag),
        "consensus": _serialisable(consensus),
        "pii": _serialisable(pii),
        "latency": _serialisable(latency),
        "chat": _serialisable(chat),
    }

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2, default=str))
    print(f"Wrote {args.out}")

    # Print a quick comparison summary to stdout.
    print()
    for label in ("haiku", "sonnet"):
        e = out["models"][label]["extraction"]
        s = out["models"][label]["source"]
        cost = (s["total_input_tokens"] or 0) / 1e6 * (1.0 if label == "haiku" else 3.0) \
             + (s["total_output_tokens"] or 0) / 1e6 * (5.0 if label == "haiku" else 15.0)
        print(f"{label:6s}  micro-F1 {e['micro_f1']*100:5.1f}%  macro-F1 {e['macro_f1']*100:5.1f}%  "
              f"coverage {e['coverage']*100:5.1f}%  halluc {e['hallucination']*100:4.1f}%  "
              f"tokens in={s['total_input_tokens']:>5} out={s['total_output_tokens']:>5}  ${cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
