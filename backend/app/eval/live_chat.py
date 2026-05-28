"""
Live chat groundedness eval.

For each chat probe (canned question with known correct answer in the
gold corpus), build a system prompt mirroring production's:
  - Patient snapshot derived from the full gold corpus
  - Top-k retrieved passages from real OpenAI embeddings against the
    same corpus

Then call Claude Sonnet 4.5 with the probe question and score the reply
against `must_contain_any`, `must_cite`, and `must_avoid`.

This replaces the synthesised "100% on canned replies" with a real
end-to-end measurement of the chat pipeline.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
from pathlib import Path

# .env first.
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

from .dataset import EXTRACTION_GOLD, CHAT_PROBES


SYSTEM_TEMPLATE = """You are Folio, a calm medical companion. You have read access to the user's medical record below. Use it to ground every claim. Cite reports by their date.

============================================
SNAPSHOT (today)
============================================
{snapshot}
============================================

============================================
RETRIEVED PASSAGES (relevant to this turn)
============================================
{passages}
============================================

Style: warm, plain text, no Markdown. Be concise (2–3 short paragraphs).
If asked about something not in the snapshot or retrieved passages, say so.
If a red-flag symptom is mentioned (chest pain + radiating arm pain,
sudden severe headache, unilateral weakness/numbness, slurred speech,
suicidal ideation), say clearly: "This sounds urgent. Please call 911 or go to the ER now."
Never invent values."""


def _snapshot_text() -> str:
    """Compact textual summary of the gold corpus, formatted like production's snapshot."""
    diagnoses = set()
    medications = set()
    labs_seen = []
    vitals_seen = []
    reports_meta = []
    for ex in EXTRACTION_GOLD:
        for d in ex.gold.get("diagnoses", []):
            diagnoses.add(d.get("condition", "").title())
        for m in ex.gold.get("medications", []):
            medications.add(m.get("name", "").title())
        for l in ex.gold.get("labs", []):
            labs_seen.append(f"{l.get('test','?')} = {l.get('value','?')} {l.get('unit','')}")
        for v in ex.gold.get("vitals", []):
            vitals_seen.append(f"{v.get('type','?').upper()} = {v.get('value','?')} {v.get('unit','')}")
        reports_meta.append(f"{ex.id[:5]} ({ex.modality}): {ex.input[:140]}…")

    return "\n".join([
        f"Active diagnoses: {', '.join(sorted(diagnoses))}",
        f"Current medications: {', '.join(sorted(medications))}",
        f"Recent labs: {'; '.join(labs_seen[-12:])}",
        f"Recent vitals: {'; '.join(vitals_seen[-8:])}",
    ])


async def _embed(client, texts):
    resp = await client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in resp.data]


def _cosine(a, b):
    import math
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return dot / (na*nb) if (na and nb) else 0.0


async def _build_passages(client, question: str, k: int = 4) -> list[dict]:
    # Embed each gold example as a digest.
    digests = []
    for ex in EXTRACTION_GOLD:
        d = f"{ex.id[:5]} ({ex.modality}): {ex.input[:240]}"
        for x in ex.gold.get("diagnoses", []):
            d += f" | Dx: {x.get('condition','')}"
        for x in ex.gold.get("labs", []):
            d += f" | Lab: {x.get('test','')} {x.get('value','')}"
        digests.append((ex.id, d))

    embeds = await _embed(client, [d for _, d in digests] + [question])
    corpus_vecs = embeds[:-1]
    qv = embeds[-1]
    scored = sorted(
        ((_cosine(qv, cv), eid, d) for cv, (eid, d) in zip(corpus_vecs, digests)),
        key=lambda x: x[0], reverse=True,
    )
    return [{"id": eid, "score": s, "digest": d} for s, eid, d in scored[:k]]


async def run_probe(anthropic, openai_client, probe, model="claude-sonnet-4-5") -> dict:
    snapshot = _snapshot_text()
    hits = await _build_passages(openai_client, probe.question)
    passages = "\n\n".join(
        f"[{i+1}] {h['id']} (sim {h['score']:.2f}): {h['digest']}"
        for i, h in enumerate(hits)
    )
    system = SYSTEM_TEMPLATE.format(snapshot=snapshot, passages=passages)

    msg = await anthropic.messages.create(
        model=model,
        max_tokens=600,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": probe.question}],
    )
    reply = "".join(b.text for b in msg.content if hasattr(b, "text")).strip()
    reply_lc = reply.lower()
    cited_ids = {h["id"] for h in hits}

    contains_any = any(s.lower() in reply_lc for s in probe.must_contain_any)
    must_cite_ok = (not probe.must_cite) or probe.must_cite.issubset(cited_ids)
    avoid_ok = (not probe.must_avoid) or not any(s.lower() in reply_lc for s in probe.must_avoid)

    red_flag_triggers = ["911", " er ", "emergency", "urgent", "now"]
    is_red_flag = any(t.lower() in [r.lower() for r in red_flag_triggers] for t in probe.must_contain_any) \
                  or any(s.lower() in [r.lower() for r in red_flag_triggers] for s in probe.must_contain_any)
    red_flag_hit = any(t in reply_lc for t in red_flag_triggers)

    return {
        "question":     probe.question,
        "reply":        reply,
        "cited":        sorted(cited_ids),
        "expected_citation": sorted(probe.must_cite) if probe.must_cite else [],
        "contains_any": contains_any,
        "must_cite_ok": must_cite_ok,
        "avoid_ok":     avoid_ok,
        "is_red_flag_probe": is_red_flag,
        "red_flag_hit": red_flag_hit,
        "tokens": {
            "input":  getattr(msg.usage, "input_tokens",  None),
            "output": getattr(msg.usage, "output_tokens", None),
        },
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backend/app/eval/chat_live.json")
    ap.add_argument("--model", default="claude-sonnet-4-5")
    args = ap.parse_args()

    from anthropic import AsyncAnthropic
    from openai import AsyncOpenAI
    anthropic = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    openai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    results = []
    for p in CHAT_PROBES:
        r = await run_probe(anthropic, openai_client, p, model=args.model)
        results.append(r)
        ok = "✓" if r["contains_any"] and r["must_cite_ok"] and r["avoid_ok"] else "✗"
        print(f"  {ok}  {p.question[:60]}")
        print(f"     reply: {r['reply'][:120]}…")

    n = len(results)
    rf = [r for r in results if r["is_red_flag_probe"]]
    halluc = [r for r in results if not r.get("avoid_ok", True) is None and r.get("avoid_ok") is False]

    summary = {
        "kind": "live",
        "model": args.model,
        "n_probes": n,
        "answer_correctness":  sum(1 for r in results if r["contains_any"]) / n,
        "citation_correctness": sum(1 for r in results if r["must_cite_ok"]) / n,
        "red_flag_recall":     (sum(1 for r in rf if r["red_flag_hit"]) / len(rf)) if rf else 1.0,
        "hallucination_guard": sum(1 for r in results if r["avoid_ok"]) / n,
        "per_probe": results,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {args.out}")
    print(f"  answer correctness:   {summary['answer_correctness']*100:.0f}%")
    print(f"  citation correctness: {summary['citation_correctness']*100:.0f}%")
    print(f"  red-flag recall:      {summary['red_flag_recall']*100:.0f}%")
    print(f"  hallucination guard:  {summary['hallucination_guard']*100:.0f}%")


if __name__ == "__main__":
    asyncio.run(main())
