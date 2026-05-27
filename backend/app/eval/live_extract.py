"""
Live-model predictions on the gold extraction set.

Runs each gold example through the real Claude API using the same
system prompt the production pipeline uses, then dumps the predictions
to a JSON file. The eval runner can be pointed at that JSON via
`--predictions <path>` to score real model output instead of the
deterministic synthetic predictions used for framework testing.

Why a separate script (vs. importing pipeline.extraction directly):
the production pipeline transitively imports redis, motor, openai,
google-generativeai — installing all of that just to run an eval is
heavy. This module is intentionally self-contained: anthropic + stdlib
only. We hard-copy the system prompt to keep it in lock-step.

Run:
    .eval-venv/bin/python -m backend.app.eval.live_extract \\
        --out backend/app/eval/predictions_live.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Allow running from the repo root: `python -m backend.app.eval.live_extract`
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.app.eval.dataset import EXTRACTION_GOLD  # noqa: E402


# Kept in sync with backend/app/pipeline/extraction.py::SYSTEM_PROMPT
SYSTEM_PROMPT = """You are a clinical information extractor. Convert the user's medical text (lab report, discharge summary, symptom note, prescription, etc.) into a single JSON object that conforms to the schema below.

Output rules:
- Output a SINGLE JSON object and nothing else. No prose, no code fences.
- Use empty arrays for sections with no information. Do not invent data.
- Capture EVERYTHING the source mentions, including labs in prose ("LDL of 142"), vitals in passing ("BP today 132/84"), and abbreviated lab names (e.g. "eGFR", "ALT", "CA 27-29").
- For diagnoses: prefer the canonical short name ("Hypertension", "Type 2 diabetes mellitus"). If the source uses a longer phrase ("Essential hypertension", "Stage IIB invasive ductal carcinoma"), use that. Include ICD-10 when the source states it or it's unambiguous.
- For diagnoses.status: one of "active", "resolved", "suspected"; confidence is 0..1.
- For labs.flag: one of "normal", "high", "low", "critical".
- For symptoms.severity: one of "mild", "moderate", "severe".
- For vitals.type: one of "bp", "hr", "temp", "spo2", "weight", "bmi", "glucose".

CRITICAL — red_flags:
- red_flags is ONLY for findings that warrant clinician attention BEYOND routine follow-up. Examples: chest pain + ST elevation; acute focal neuro deficit; signs of sepsis; suicidal ideation; visible TEN/SJS pattern.
- DO NOT put routine concerning labs (mildly elevated LDL, A1C uptrending within outpatient management) into red_flags. Those are just labs.
- DO NOT put garden-variety symptoms (a multi-day headache without warning signs, fatigue, mild GI upset) into red_flags. Those are just symptoms.
- If unsure, leave red_flags empty. False red flags are worse than missed routine findings.
- For red_flags.urgency: one of "routine", "soon", "urgent", "emergent". Use "emergent" only for true emergencies.

raw_summary: 1–2 plain-English sentences covering the gist.

Order fields exactly: diagnoses, medications, vitals, labs, symptoms, red_flags, raw_summary. (This lets the UI render progressively as the stream arrives.)

Schema:
{
  "diagnoses": [{"condition": "", "icd10": "", "status": "active", "confidence": 0.0}],
  "medications": [{"name": "", "dose": "", "frequency": "", "started_at": "", "purpose": ""}],
  "vitals": [{"type": "bp", "value": "", "unit": "", "recorded_at": ""}],
  "labs": [{"test": "", "value": "", "unit": "", "reference_range": "", "flag": "normal"}],
  "symptoms": [{"description": "", "onset": "", "severity": "mild"}],
  "red_flags": [{"finding": "", "reason": "", "urgency": "routine"}],
  "raw_summary": ""
}
"""


def _safe_parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return {}
    try:
        return json.loads(text[s : e + 1])
    except Exception:
        return {}


async def predict_one(client, model: str, user_text: str) -> tuple[dict, dict]:
    """Returns (parsed_prediction, meta)."""
    t0 = time.perf_counter()
    msg = await client.messages.create(
        model=model,
        max_tokens=2000,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": f"Extract structured medical data from the following text:\n\n---\n{user_text}\n---"}],
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000

    text = "".join(b.text for b in msg.content if hasattr(b, "text"))
    parsed = _safe_parse_json(text)
    usage = getattr(msg, "usage", None)
    meta = {
        "elapsed_ms": round(elapsed_ms, 1),
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None) if usage else None,
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None) if usage else None,
        "raw_chars": len(text),
        "parsed_ok": bool(parsed),
    }
    return parsed, meta


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backend/app/eval/predictions_live.json")
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="Anthropic model id. Defaults to claude-haiku-4-5 (hot-path).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run the first N gold examples (cost-control).")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"loaded {env_path}")
    else:
        print(f"no .env at {env_path}")
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("ANTHROPIC_API_KEY missing. Set it in .env first.")
        sys.exit(1)

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic(api_key=key)

    examples = EXTRACTION_GOLD if args.limit is None else EXTRACTION_GOLD[:args.limit]
    predictions: dict[str, dict] = {}
    meta_per: dict[str, dict] = {}
    total_in = total_out = 0
    failed: list[str] = []

    print(f"Running {len(examples)} examples against {args.model} …")
    for i, ex in enumerate(examples, 1):
        if ex.modality in ("image",):
            # Skip vision-only examples — the hot-path text extractor can't see them.
            # A separate live_vision.py would run vision_clinical_extract instead.
            print(f"  [{i:2}/{len(examples)}] {ex.id:30s}  SKIP (vision-only)")
            predictions[ex.id] = {}
            continue

        text = ex.input
        try:
            pred, meta = await predict_one(client, args.model, text)
            predictions[ex.id] = pred
            meta_per[ex.id] = meta
            total_in += (meta.get("input_tokens") or 0)
            total_out += (meta.get("output_tokens") or 0)
            ok = "✓" if meta["parsed_ok"] else "✗"
            print(f"  [{i:2}/{len(examples)}] {ex.id:30s}  {ok}  {meta['elapsed_ms']:>6.0f} ms  "
                  f"{meta.get('input_tokens') or 0:>5} in / {meta.get('output_tokens') or 0:>4} out")
        except Exception as e:
            failed.append(f"{ex.id}: {e}")
            predictions[ex.id] = {}
            print(f"  [{i:2}/{len(examples)}] {ex.id:30s}  FAIL  {e}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "model": args.model,
        "n": len(examples),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "failed": failed,
        "meta": meta_per,
        "predictions": predictions,
    }, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Total tokens: {total_in} in, {total_out} out")
    # Claude Haiku 4.5 list price ~ $1.00 / Mtok in, $5.00 / Mtok out (approx).
    cost = total_in / 1e6 * 1.00 + total_out / 1e6 * 5.00
    print(f"Approx cost: ${cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
