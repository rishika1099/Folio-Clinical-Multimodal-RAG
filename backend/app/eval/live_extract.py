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


async def predict_anthropic(client, model: str, user_text: str) -> tuple[dict, dict]:
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
        "elapsed_ms": round(elapsed_ms, 1), "model": model,
        "input_tokens":  getattr(usage, "input_tokens", None)  if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
        "parsed_ok": bool(parsed),
    }
    return parsed, meta


async def predict_openai(client, model: str, user_text: str) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=2000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract structured medical data from the following text:\n\n---\n{user_text}\n---"},
        ],
        response_format={"type": "json_object"},
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000
    text = resp.choices[0].message.content or ""
    parsed = _safe_parse_json(text)
    usage = getattr(resp, "usage", None)
    meta = {
        "elapsed_ms": round(elapsed_ms, 1), "model": model,
        "input_tokens":  getattr(usage, "prompt_tokens", None)     if usage else None,
        "output_tokens": getattr(usage, "completion_tokens", None) if usage else None,
        "parsed_ok": bool(parsed),
    }
    return parsed, meta


async def predict_gemini(genai, model_name: str, user_text: str) -> tuple[dict, dict]:
    import asyncio as _aio
    loop = _aio.get_event_loop()
    t0 = time.perf_counter()
    def _do():
        m = genai.GenerativeModel(model_name, system_instruction=SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json", "max_output_tokens": 2000})
        return m.generate_content(
            f"Extract structured medical data from the following text:\n\n---\n{user_text}\n---"
        )
    resp = await loop.run_in_executor(None, _do)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    text = getattr(resp, "text", "") or ""
    parsed = _safe_parse_json(text)
    um = getattr(resp, "usage_metadata", None)
    meta = {
        "elapsed_ms": round(elapsed_ms, 1), "model": model_name,
        "input_tokens":  getattr(um, "prompt_token_count", None)     if um else None,
        "output_tokens": getattr(um, "candidates_token_count", None) if um else None,
        "parsed_ok": bool(parsed),
    }
    return parsed, meta


def _provider_for(model: str) -> str:
    if model.startswith("claude"): return "anthropic"
    if model.startswith("gpt"):     return "openai"
    if model.startswith("gemini"):  return "gemini"
    raise SystemExit(f"unknown provider for model {model!r}")


def _approx_cost(provider: str, model: str, tin: int, tout: int) -> float:
    # Rough list prices in $/Mtok as of mid-2026; close enough for an
    # eval cost estimate. Real billing uses provider invoices.
    rates = {
        ("anthropic", "haiku"):  (1.0,  5.0),
        ("anthropic", "sonnet"): (3.0, 15.0),
        ("openai",    "gpt-4.1"): (2.0,  8.0),
        ("openai",    "gpt-4.1-mini"): (0.4, 1.6),
        ("gemini",    "flash"):  (0.0,  0.0),   # free tier
        ("gemini",    "pro"):    (0.0,  0.0),
    }
    key = "haiku" if "haiku" in model else \
          "sonnet" if "sonnet" in model else \
          "gpt-4.1-mini" if "mini" in model else \
          "gpt-4.1" if "gpt-4.1" in model else \
          "flash" if "flash" in model else "pro"
    r_in, r_out = rates.get((provider, key), (0.0, 0.0))
    return tin / 1e6 * r_in + tout / 1e6 * r_out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backend/app/eval/predictions_live.json")
    ap.add_argument("--model", default="claude-haiku-4-5",
                    help="Model id. Provider inferred from prefix (claude-/gpt-/gemini-).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Only run the first N gold examples (cost-control).")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[3]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"loaded {env_path}")

    provider = _provider_for(args.model)
    client = None
    genai = None
    if provider == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key: sys.exit("ANTHROPIC_API_KEY missing")
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=key)
    elif provider == "openai":
        key = os.environ.get("OPENAI_API_KEY")
        if not key: sys.exit("OPENAI_API_KEY missing")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=key)
    elif provider == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key: sys.exit("GEMINI_API_KEY missing")
        import google.generativeai as gen
        gen.configure(api_key=key)
        genai = gen

    examples = EXTRACTION_GOLD if args.limit is None else EXTRACTION_GOLD[:args.limit]
    predictions: dict[str, dict] = {}
    meta_per: dict[str, dict] = {}
    total_in = total_out = 0
    failed: list[str] = []

    print(f"Running {len(examples)} examples against {args.model} (provider={provider}) …")
    for i, ex in enumerate(examples, 1):
        if ex.modality in ("image",):
            print(f"  [{i:2}/{len(examples)}] {ex.id:30s}  SKIP (vision-only)")
            predictions[ex.id] = {}
            continue

        try:
            if provider == "anthropic":
                pred, meta = await predict_anthropic(client, args.model, ex.input)
            elif provider == "openai":
                pred, meta = await predict_openai(client, args.model, ex.input)
            else:
                # Gemini free tier is 10 RPM — throttle so we don't 429.
                pred, meta = await predict_gemini(genai, args.model, ex.input)
                await asyncio.sleep(7)
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
            print(f"  [{i:2}/{len(examples)}] {ex.id:30s}  FAIL  {str(e)[:120]}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cost = _approx_cost(provider, args.model, total_in, total_out)
    out_path.write_text(json.dumps({
        "model": args.model,
        "provider": provider,
        "n": len(examples),
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "approx_cost_usd": cost,
        "failed": failed,
        "meta": meta_per,
        "predictions": predictions,
    }, indent=2))
    print(f"\nWrote {out_path}")
    print(f"Total tokens: {total_in} in, {total_out} out")
    print(f"Approx cost: ${cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
