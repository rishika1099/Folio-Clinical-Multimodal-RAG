from fastapi import APIRouter, HTTPException

from ..db import get_db
from ..suggestions.runner import run_all

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


@router.get("")
async def list_suggestions(category: str | None = None, severity: str | None = None,
                            include_dismissed: bool = False):
    db = get_db()
    q: dict = {}
    if not include_dismissed:
        q["dismissed"] = {"$ne": True}
    if category:
        q["category"] = category
    if severity:
        q["severity"] = severity
    rows = await db.suggestions.find(q, {"_id": 0}).sort([("severity", -1), ("created_at", -1)]).limit(200).to_list(length=200)
    return {"suggestions": rows}


@router.post("/{suggestion_id}/dismiss")
async def dismiss(suggestion_id: str):
    db = get_db()
    res = await db.suggestions.update_one({"suggestion_id": suggestion_id}, {"$set": {"dismissed": True}})
    if res.matched_count == 0:
        raise HTTPException(404, "not found")
    # Move to dismissed_suggestions for audit (optional).
    doc = await db.suggestions.find_one({"suggestion_id": suggestion_id}, {"_id": 0})
    if doc:
        await db.dismissed_suggestions.insert_one(doc)
    return {"ok": True}


@router.post("/regenerate/{report_id}")
async def regenerate(report_id: str):
    out = await run_all(report_id)
    return {"generated": len(out)}
