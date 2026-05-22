"""
Consensus extraction endpoint. Slower than the hot-path single-model
ingest, but produces a per-field agreement score across three providers.
Surfaced behind a "High-confidence mode" toggle in the UI.
"""
import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..db import get_db
from ..pipeline.consensus import consensus_extract
from ..pipeline.persist import persist_report
from ..pipeline.pii import scrub
from ..rag.store import reindex_all
from ..schemas import ExtractedReport
from ..suggestions.runner import run_all

router = APIRouter(prefix="/api/consensus", tags=["consensus"])


@router.post("")
async def run_consensus(payload: dict):
    text = (payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    input_type = payload.get("input_type") or "text"

    scrubbed = scrub(text)
    try:
        result = await consensus_extract(scrubbed)
    except Exception as e:
        raise HTTPException(502, f"consensus failed: {e}")

    data = result["report"]
    meta = result["consensus"]

    report = ExtractedReport(input_type=input_type, source_text=text, **data,
                              model_used="ensemble:" + ",".join(meta["models_succeeded"]),
                              latency_ms={"consensus_total_ms": meta["elapsed_ms"]})
    await persist_report(report)

    # Persist consensus metadata next to the report for later display.
    db = get_db()
    await db.consensus_meta.update_one(
        {"report_id": report.report_id},
        {"$set": {"report_id": report.report_id, **meta}},
        upsert=True,
    )

    # Fire-and-forget suggestions.
    asyncio.create_task(run_all(report.report_id))

    return JSONResponse({
        "report": report.model_dump(),
        "consensus": meta,
    })


@router.get("/{report_id}")
async def get_consensus(report_id: str):
    db = get_db()
    doc = await db.consensus_meta.find_one({"report_id": report_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "no consensus metadata for this report")
    return doc


@router.post("/reindex")
async def reindex():
    """Manual trigger to rebuild all RAG embeddings."""
    try:
        n = await reindex_all()
    except Exception as e:
        raise HTTPException(500, f"reindex failed: {e}")
    return {"indexed": n}
