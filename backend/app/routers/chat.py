"""
Conversational endpoint. Streams Claude Sonnet's response token-by-token
over SSE. Every turn pulls the current user's health snapshot from Mongo
and the top-k retrieved passages from their personal RAG index, then
injects both into the system prompt.
"""
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..auth import require_auth
from ..config import settings
from ..db import get_db
from ..models.router import (
    ROUTE_REASON_FALLBACK,
    ROUTE_REASON_PRIMARY,
    _anthropic_client,
    _openai_client,
    transcribe_audio,
)
from ..rag.store import retrieve_with_timing
from ..schemas import UserPublic

router = APIRouter(prefix="/api/chat", tags=["chat"])


SYSTEM_TEMPLATE = """You are Folio, a calm, careful medical companion for {name}.
Your role is to help them:
1. Talk through how they're feeling today — symptoms, mood, energy, anything on their mind.
2. Make sense of their own medical record (active conditions, medications, recent vitals/labs).
3. Decide whether something they're noticing warrants a clinician's attention.

You have two pieces of grounding context:
  (a) A SNAPSHOT of their current state.
  (b) RETRIEVED PASSAGES from their reports, most relevant to this turn.

Use both to keep every specific claim grounded. Never invent values or
thresholds. If a claim is not supported by either context block, say so.

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

Style:
- Warm, plain language. You're a thoughtful first listener, not a doctor.
- Be concise. Default to 2–4 short paragraphs unless they ask for depth.
- Ask one focused follow-up question when more detail would help.
- If they mention a red-flag symptom (chest pain with shortness of breath
  or radiating arm pain, sudden severe headache, unilateral weakness or
  numbness, slurred speech, fainting, suicidal thoughts), stop and say
  clearly: "This sounds urgent. Please call 911 or go to the ER now."
- Never diagnose, never prescribe, never invent dosages.
- When they ask about their own data, answer directly using snapshot or
  retrieved passages. No hedging on facts they can verify.
- Address the user as {name}.
- If a question is outside medical scope, gently redirect.
"""


async def _build_snapshot(user_id: str) -> str:
    db = get_db()

    actives = await db.diagnoses_master.find(
        {"user_id": user_id, "status": "active"}, {"_id": 0}
    ).sort("last_seen", -1).to_list(length=20)

    meds = await db.medications_master.find(
        {"user_id": user_id, "active": True}, {"_id": 0}
    ).sort("last_seen", -1).to_list(length=30)

    vital_types = ["bp", "hr", "weight", "bmi", "spo2", "glucose", "temp"]
    latest_vitals = {}
    for vt in vital_types:
        v = await db.vitals_timeline.find_one(
            {"user_id": user_id, "type": vt}, sort=[("recorded_at", -1)]
        )
        if v:
            latest_vitals[vt] = {"value": v.get("value"), "unit": v.get("unit"),
                                  "recorded_at": v.get("recorded_at")}

    recent_labs = await db.labs_timeline.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("recorded_at", -1).limit(15).to_list(length=15)

    recent_reports = await db.reports.find(
        {"user_id": user_id},
        {"_id": 0, "uploaded_at": 1, "input_type": 1, "raw_summary": 1},
    ).sort("uploaded_at", -1).limit(5).to_list(length=5)

    open_flags = await db.reports.aggregate([
        {"$match": {"user_id": user_id}},
        {"$sort": {"uploaded_at": -1}}, {"$limit": 10},
        {"$unwind": "$red_flags"},
        {"$project": {"_id": 0, "finding": "$red_flags.finding",
                      "reason": "$red_flags.reason", "urgency": "$red_flags.urgency"}},
        {"$limit": 6},
    ]).to_list(length=6)

    lines: list[str] = []
    lines.append(f"Active conditions ({len(actives)}):")
    if actives:
        for d in actives:
            lines.append(f"  - {d.get('condition','?').title()} ({d.get('icd10','—')})")
    else:
        lines.append("  (none recorded)")
    lines.append("")
    lines.append(f"Current medications ({len(meds)}):")
    if meds:
        for m in meds:
            lines.append(f"  - {m.get('display_name') or m.get('name','?').title()} "
                          f"{m.get('dose','')} {m.get('frequency','')} — {m.get('purpose','')}".strip())
    else:
        lines.append("  (none recorded)")
    lines.append("")
    lines.append("Latest vitals:")
    if latest_vitals:
        for vt, v in latest_vitals.items():
            lines.append(f"  - {vt.upper()}: {v['value']} {v.get('unit','')} ({str(v.get('recorded_at',''))[:10]})")
    else:
        lines.append("  (none recorded)")
    lines.append("")
    lines.append("Recent labs (last 15):")
    if recent_labs:
        for l in recent_labs:
            flag = f" [{l['flag']}]" if l.get("flag") and l["flag"] != "normal" else ""
            lines.append(f"  - {l.get('test','?')}: {l.get('value','?')} {l.get('unit','')} "
                          f"(ref {l.get('reference_range','—')}){flag} on {str(l.get('recorded_at',''))[:10]}")
    else:
        lines.append("  (none recorded)")
    if open_flags:
        lines.append("")
        lines.append("Recent red flags surfaced from reports:")
        for f in open_flags:
            lines.append(f"  - {f['finding']} — {f['reason']} (urgency: {f['urgency']})")
    if recent_reports:
        lines.append("")
        lines.append("Recent report summaries:")
        for r in recent_reports:
            lines.append(f"  - {str(r.get('uploaded_at',''))[:10]} ({r.get('input_type','')}): "
                          f"{r.get('raw_summary','')}")
    return "\n".join(lines)


def _sse(event: str, data) -> bytes:
    payload = data if isinstance(data, str) else json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n".encode()


async def _stream_anthropic(system: str, messages: list[dict]) -> AsyncIterator[str]:
    client = _anthropic_client()
    if client is None:
        raise RuntimeError("anthropic_key_missing")
    async with client.messages.stream(
        model=ROUTE_REASON_PRIMARY.model,
        max_tokens=1024,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _stream_openai(system: str, messages: list[dict]) -> AsyncIterator[str]:
    client = _openai_client()
    if client is None:
        raise RuntimeError("openai_key_missing")
    resp = await client.chat.completions.create(
        model=ROUTE_REASON_FALLBACK.model,
        messages=[{"role": "system", "content": system}, *messages],
        stream=True,
        max_tokens=1024,
    )
    async for chunk in resp:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta


@router.get("/snapshot")
async def snapshot(user: UserPublic = Depends(require_auth)):
    db = get_db()
    actives = await db.diagnoses_master.count_documents({"user_id": user.user_id, "status": "active"})
    meds = await db.medications_master.count_documents({"user_id": user.user_id, "active": True})
    last_vital = await db.vitals_timeline.find_one(
        {"user_id": user.user_id}, sort=[("recorded_at", -1)]
    )
    last_report = await db.reports.find_one(
        {"user_id": user.user_id}, sort=[("uploaded_at", -1)]
    )
    return {
        "active_conditions": actives,
        "active_medications": meds,
        "last_vital_at": last_vital.get("recorded_at") if last_vital else None,
        "last_report_at": last_report.get("uploaded_at") if last_report else None,
        "has_anthropic": bool(settings.anthropic_api_key),
        "has_openai": bool(settings.openai_api_key),
    }


@router.post("")
async def chat(payload: dict, user: UserPublic = Depends(require_auth)):
    messages = payload.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise HTTPException(400, "messages required")

    name = user.display_name or user.username
    snapshot_text = await _build_snapshot(user.user_id)

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    try:
        hits, rag_timing = await retrieve_with_timing(last_user, user_id=user.user_id, k=4)
    except Exception:
        hits, rag_timing = [], {"embed_ms": 0, "search_ms": 0}

    if hits:
        passages = "\n\n".join(
            f"[{i+1}] {h.get('uploaded_at','')[:10]} ({h.get('input_type','')}, "
            f"sim={h.get('score',0):.2f}): {h.get('digest','')}"
            for i, h in enumerate(hits)
        )
    else:
        passages = "(no prior reports retrieved for this query)"
    system = SYSTEM_TEMPLATE.format(name=name, snapshot=snapshot_text, passages=passages)

    clean: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            clean.append({"role": role, "content": content})
    if not clean or clean[-1]["role"] != "user":
        raise HTTPException(400, "last message must be from user")

    has_anthropic = bool(settings.anthropic_api_key)
    has_openai = bool(settings.openai_api_key)

    if not (has_anthropic or has_openai):
        async def err_only():
            yield _sse("error", {"message": "No language-model API key configured on this server."})
            yield _sse("done", {})
        return StreamingResponse(err_only(), media_type="text/event-stream")

    async def gen():
        yield _sse("rag", {
            "hits": [{"report_id": h["report_id"], "uploaded_at": h["uploaded_at"],
                      "input_type": h["input_type"], "score": h["score"]} for h in hits],
            "timing_ms": rag_timing,
        })
        try:
            stream = _stream_anthropic(system, clean) if has_anthropic else _stream_openai(system, clean)
            async for piece in stream:
                yield _sse("delta", piece)
        except Exception as e:
            try:
                fallback = _stream_openai(system, clean) if has_anthropic and has_openai else None
                if fallback:
                    async for piece in fallback:
                        yield _sse("delta", piece)
                else:
                    yield _sse("error", {"message": f"Chat failed: {e}"})
            except Exception as e2:
                yield _sse("error", {"message": f"Chat failed: {e2}"})
        yield _sse("done", {})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/transcribe")
async def transcribe_voice(file: UploadFile = File(...),
                            user: UserPublic = Depends(require_auth)):
    audio = await file.read()
    if not audio:
        raise HTTPException(400, "empty audio")
    mime = file.content_type or "audio/webm"
    try:
        text = await transcribe_audio(audio, mime=mime)
    except Exception as e:
        raise HTTPException(500, f"transcription failed: {e}")
    return {"transcript": text}
