"""Dev-panel endpoints. Latency stats, model routing visibility."""
from fastapi import APIRouter

from ..db import get_db
from ..models.router import (
    ROUTE_EXTRACT_FALLBACK,
    ROUTE_EXTRACT_PRIMARY,
    ROUTE_REASON_FALLBACK,
    ROUTE_REASON_PRIMARY,
    ROUTE_SUMMARIZE_FALLBACK,
    ROUTE_SUMMARIZE_PRIMARY,
    ROUTE_TRANSCRIBE_FALLBACK,
    ROUTE_TRANSCRIBE_PRIMARY,
    ROUTE_VISION_FALLBACK,
    ROUTE_VISION_PRIMARY,
)

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.get("/routes")
def routes():
    """Returns the full model routing table — used by the dev panel."""
    def _row(name, primary, fallback):
        return {
            "task": name,
            "primary": {"provider": primary.provider, "model": primary.model, "reason": primary.reason},
            "fallback": {"provider": fallback.provider, "model": fallback.model, "reason": fallback.reason},
        }
    return {"routes": [
        _row("extract_json (hot path)", ROUTE_EXTRACT_PRIMARY, ROUTE_EXTRACT_FALLBACK),
        _row("vision_ocr", ROUTE_VISION_PRIMARY, ROUTE_VISION_FALLBACK),
        _row("transcribe_audio", ROUTE_TRANSCRIBE_PRIMARY, ROUTE_TRANSCRIBE_FALLBACK),
        _row("medical_reasoning (cold)", ROUTE_REASON_PRIMARY, ROUTE_REASON_FALLBACK),
        _row("summarize", ROUTE_SUMMARIZE_PRIMARY, ROUTE_SUMMARIZE_FALLBACK),
    ]}


@router.get("/latency")
async def latency_stats(limit: int = 50):
    """Aggregates per-stage latency from the last N reports."""
    db = get_db()
    rows = await db.reports.find(
        {"latency_ms": {"$exists": True}},
        {"_id": 0, "report_id": 1, "uploaded_at": 1, "input_type": 1, "model_used": 1, "latency_ms": 1},
    ).sort("uploaded_at", -1).limit(limit).to_list(length=limit)

    if not rows:
        return {"reports": [], "summary": {}}

    totals = [r["latency_ms"].get("total_ms", 0) for r in rows if r.get("latency_ms")]
    totals_sorted = sorted(totals)
    def pct(p):
        if not totals_sorted:
            return 0
        idx = max(0, int(len(totals_sorted) * p) - 1)
        return totals_sorted[idx]

    return {
        "reports": rows,
        "summary": {
            "n": len(totals),
            "p50_ms": pct(0.5),
            "p95_ms": pct(0.95),
            "p99_ms": pct(0.99),
        },
    }


@router.get("/health")
async def health():
    db = get_db()
    try:
        await db.command("ping")
        mongo_ok = True
    except Exception:
        mongo_ok = False
    return {"mongo": mongo_ok}
