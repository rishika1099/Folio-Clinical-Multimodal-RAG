"""Dashboard read endpoints. Single $facet aggregation for the overview."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import require_auth
from ..db import get_db
from ..schemas import UserPublic
from ..storage import open_attachment

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/overview")
async def overview(user: UserPublic = Depends(require_auth)):
    db = get_db()
    uid = user.user_id

    pipe = [
        {"$match": {"user_id": uid}},
        {"$facet": {
            "active_diagnoses": [
                {"$match": {"status": "active"}},
                {"$sort": {"last_seen": -1}},
                {"$limit": 20},
                {"$project": {"_id": 0}},
            ],
        }},
    ]
    dx_facet = await db.diagnoses_master.aggregate(pipe).to_list(length=1)
    active_dx = (dx_facet[0] if dx_facet else {}).get("active_diagnoses", [])

    active_meds = await db.medications_master.find(
        {"user_id": uid, "active": True}, {"_id": 0}
    ).sort("last_seen", -1).limit(30).to_list(length=30)

    latest_vitals = {}
    for vtype in ["bp", "hr", "temp", "spo2", "weight", "bmi", "glucose"]:
        v = await db.vitals_timeline.find_one(
            {"user_id": uid, "type": vtype}, sort=[("recorded_at", -1)]
        )
        if v:
            v.pop("_id", None)
            latest_vitals[vtype] = v

    top_suggestions = await db.suggestions.find(
        {"user_id": uid, "dismissed": {"$ne": True}}, {"_id": 0}
    ).sort([("severity", -1), ("created_at", -1)]).limit(3).to_list(length=3)

    red_flags = await db.reports.aggregate([
        {"$match": {"user_id": uid}},
        {"$sort": {"uploaded_at": -1}},
        {"$limit": 20},
        {"$unwind": "$red_flags"},
        {"$project": {"_id": 0, "report_id": 1, "uploaded_at": 1,
                      "finding": "$red_flags.finding",
                      "reason": "$red_flags.reason",
                      "urgency": "$red_flags.urgency"}},
        {"$limit": 10},
    ]).to_list(length=10)

    return {
        "active_diagnoses": active_dx,
        "active_medications": active_meds,
        "latest_vitals": latest_vitals,
        "top_suggestions": top_suggestions,
        "red_flags": red_flags,
    }


@router.get("/timeline")
async def timeline(limit: int = 50, user: UserPublic = Depends(require_auth)):
    db = get_db()
    reports = await db.reports.find(
        {"user_id": user.user_id}, {"_id": 0}
    ).sort("uploaded_at", -1).limit(limit).to_list(length=limit)
    return {"reports": reports}


@router.get("/timeline/vitals/{vtype}")
async def vitals_series(vtype: str, limit: int = 30, user: UserPublic = Depends(require_auth)):
    db = get_db()
    rows = await db.vitals_timeline.find(
        {"user_id": user.user_id, "type": vtype}, {"_id": 0}
    ).sort("recorded_at", 1).limit(limit).to_list(length=limit)
    return {"type": vtype, "points": rows}


@router.get("/timeline/labs/{test}")
async def labs_series(test: str, limit: int = 30, user: UserPublic = Depends(require_auth)):
    db = get_db()
    rows = await db.labs_timeline.find(
        {"user_id": user.user_id, "test": {"$regex": f"^{test}$", "$options": "i"}},
        {"_id": 0},
    ).sort("recorded_at", 1).limit(limit).to_list(length=limit)
    return {"test": test, "points": rows}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, user: UserPublic = Depends(require_auth)):
    db = get_db()
    report = await db.reports.find_one(
        {"user_id": user.user_id, "report_id": report_id}, {"_id": 0}
    )
    if not report:
        raise HTTPException(404, "report not found")
    suggestions = await db.suggestions.find(
        {"user_id": user.user_id, "report_id": report_id}, {"_id": 0}
    ).to_list(length=100)
    consensus = await db.consensus_meta.find_one(
        {"user_id": user.user_id, "report_id": report_id}, {"_id": 0}
    )
    return {"report": report, "suggestions": suggestions, "consensus": consensus}


@router.get("/reports/{report_id}/attachment")
async def download_attachment(report_id: str, inline: bool = True,
                               user: UserPublic = Depends(require_auth)):
    db = get_db()
    report = await db.reports.find_one(
        {"user_id": user.user_id, "report_id": report_id},
        {"attachment_id": 1, "attachment_filename": 1, "attachment_mime": 1},
    )
    if not report or not report.get("attachment_id"):
        raise HTTPException(404, "no attachment for this report")
    try:
        mime, filename, stream = await open_attachment(report["attachment_id"])
    except Exception as e:
        raise HTTPException(404, f"attachment unavailable: {e}")
    disp = "inline" if inline else "attachment"
    return StreamingResponse(
        stream, media_type=mime,
        headers={"Content-Disposition": f'{disp}; filename="{filename}"'},
    )
