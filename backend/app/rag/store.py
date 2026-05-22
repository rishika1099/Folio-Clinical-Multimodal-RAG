"""
Vector store for report passages. Brute-force cosine over Mongo —
fine for a single-user workload (<1000 reports). If the corpus ever
grew, swap to Atlas Vector Search or pgvector without changing the API.

Each report is split into one or more "passages" (a passage is the
raw_summary + structured-data digest). On chat we retrieve the top-k
passages by cosine similarity to the query embedding, then inject the
matched passages into the system prompt as cited evidence.
"""
import time
from datetime import datetime
from typing import Any

from ..db import get_db
from .embeddings import cosine, embed_many, embed_one


def _digest(report: dict) -> str:
    """One self-contained text block representing the report."""
    parts: list[str] = []
    parts.append(f"Report from {str(report.get('uploaded_at',''))[:10]} ({report.get('input_type','')}).")
    if report.get("raw_summary"):
        parts.append(report["raw_summary"])
    for d in report.get("diagnoses", []):
        parts.append(f"Diagnosis: {d.get('condition','')} ({d.get('icd10','')}), status {d.get('status','')}.")
    for m in report.get("medications", []):
        parts.append(f"Medication: {m.get('name','')} {m.get('dose','')} {m.get('frequency','')} for {m.get('purpose','')}.")
    for v in report.get("vitals", []):
        parts.append(f"Vital: {v.get('type','').upper()} {v.get('value','')} {v.get('unit','')}.")
    for l in report.get("labs", []):
        flag = f" [{l['flag']}]" if l.get("flag") and l["flag"] != "normal" else ""
        parts.append(f"Lab: {l.get('test','')} {l.get('value','')} {l.get('unit','')} ref {l.get('reference_range','')}{flag}.")
    for s in report.get("symptoms", []):
        parts.append(f"Symptom: {s.get('description','')} (onset {s.get('onset','')}, severity {s.get('severity','')}).")
    for f in report.get("red_flags", []):
        parts.append(f"Red flag: {f.get('finding','')} — {f.get('reason','')} (urgency {f.get('urgency','')}).")
    return " ".join(parts)


async def index_report(report: dict) -> None:
    """Compute the embedding for a report and store it."""
    db = get_db()
    digest = _digest(report)
    vec = await embed_one(digest)
    await db.report_embeddings.update_one(
        {"report_id": report["report_id"]},
        {"$set": {
            "report_id": report["report_id"],
            "uploaded_at": report.get("uploaded_at"),
            "input_type": report.get("input_type"),
            "digest": digest,
            "embedding": vec,
            "indexed_at": datetime.utcnow().isoformat(),
        }},
        upsert=True,
    )


async def reindex_all() -> int:
    """Reindex every report — used by the seed and as an admin tool."""
    db = get_db()
    reports = await db.reports.find({}, {"_id": 0}).to_list(length=10_000)
    if not reports:
        return 0
    digests = [_digest(r) for r in reports]
    vectors = await embed_many(digests)
    ops = []
    now = datetime.utcnow().isoformat()
    for r, d, v in zip(reports, digests, vectors):
        ops.append({
            "report_id": r["report_id"],
            "uploaded_at": r.get("uploaded_at"),
            "input_type": r.get("input_type"),
            "digest": d,
            "embedding": v,
            "indexed_at": now,
        })
    await db.report_embeddings.delete_many({})
    if ops:
        await db.report_embeddings.insert_many(ops)
    return len(ops)


async def retrieve(query: str, k: int = 4, min_score: float = 0.18) -> list[dict]:
    """Return the top-k report digests by cosine similarity to the query."""
    db = get_db()
    qv = await embed_one(query)
    cursor = db.report_embeddings.find({}, {"_id": 0})
    scored: list[tuple[float, dict]] = []
    async for doc in cursor:
        s = cosine(qv, doc.get("embedding") or [])
        if s >= min_score:
            scored.append((s, doc))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for s, d in scored[:k]:
        out.append({
            "report_id": d["report_id"],
            "uploaded_at": d.get("uploaded_at"),
            "input_type": d.get("input_type"),
            "digest": d["digest"],
            "score": round(s, 4),
        })
    return out


async def retrieve_with_timing(query: str, k: int = 4) -> tuple[list[dict], dict]:
    t0 = time.perf_counter()
    qv = await embed_one(query)
    t_embed = (time.perf_counter() - t0) * 1000
    t0 = time.perf_counter()
    db = get_db()
    cursor = db.report_embeddings.find({}, {"_id": 0})
    scored = []
    async for doc in cursor:
        s = cosine(qv, doc.get("embedding") or [])
        scored.append((s, doc))
    scored.sort(key=lambda t: t[0], reverse=True)
    t_search = (time.perf_counter() - t0) * 1000
    out = [{
        "report_id": d["report_id"],
        "uploaded_at": d.get("uploaded_at"),
        "input_type": d.get("input_type"),
        "digest": d["digest"],
        "score": round(s, 4),
    } for s, d in scored[:k] if s >= 0.18]
    return out, {"embed_ms": t_embed, "search_ms": t_search}
