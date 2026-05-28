"""
User self-service endpoints.

GET    /api/me/export   — returns a JSON bundle of everything Folio has on you.
DELETE /api/me          — irreversibly deletes account + all related data.

Both are scoped strictly to the calling user. Audit-logged.
"""
from __future__ import annotations

import json
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import require_auth
from ..audit import log_event
from ..db import get_db
from ..schemas import UserPublic
from ..storage import _bucket

router = APIRouter(prefix="/api/me", tags=["me"])

# Collections that hold per-user data. Used for both export and delete.
USER_COLLECTIONS = [
    "reports",
    "diagnoses_master",
    "medications_master",
    "vitals_timeline",
    "labs_timeline",
    "report_embeddings",
    "suggestions",
    "dismissed_suggestions",
    "consensus_meta",
]


def _json_default(obj):
    """JSON-serialise ObjectId, datetime, and similar Mongo types."""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"Not JSON serialisable: {type(obj)}")


@router.get("/export")
async def export_my_data(user: UserPublic = Depends(require_auth)):
    """JSON dump of every Mongo document tagged with this user_id.

    Excludes GridFS file bytes (those would balloon the response) but
    includes attachment_ids — the user can fetch the original files
    separately from /api/reports/<id>/attachment if needed.
    """
    db = get_db()
    bundle: dict = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "display_name": user.display_name,
        },
        "collections": {},
    }
    for col in USER_COLLECTIONS:
        items = await db[col].find({"user_id": user.user_id}).to_list(length=10_000)
        bundle["collections"][col] = items

    await log_event(user.user_id, "export", "self", meta={"collections": list(bundle["collections"].keys())})

    payload = json.dumps(bundle, default=_json_default, indent=2)
    filename = f"folio-{user.username}-{datetime.utcnow().strftime('%Y%m%d')}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit")
async def my_recent_audit(limit: int = 50, user: UserPublic = Depends(require_auth)):
    """Most recent audit events for this user. Used by the Profile page."""
    from ..audit import recent_events
    events = await recent_events(user.user_id, limit=limit)
    # Stringify datetimes for JSON.
    return {"events": [
        {**e, "ts": e["ts"].isoformat() if hasattr(e.get("ts"), "isoformat") else e.get("ts")}
        for e in events
    ]}


@router.delete("")
async def delete_my_account(
    payload: dict | None = None,
    user: UserPublic = Depends(require_auth),
):
    """Permanently wipe the account and everything attached to it.

    Requires `{"confirm": "<username>"}` in the body so a mis-routed click
    can't nuke a record. Audit-logs the request BEFORE the delete so we
    have a record even after the user row is gone.
    """
    payload = payload or {}
    confirm = (payload.get("confirm") or "").strip().lower()
    if confirm != user.username.lower():
        raise HTTPException(400, "Type your username to confirm deletion")

    db = get_db()

    # Audit FIRST — if delete partially fails we still have a record.
    await log_event(user.user_id, "delete_account", "self",
                    meta={"username": user.username})

    # 1) Drop all GridFS attachments owned by this user. We find attachment
    #    ids on the reports collection first, then unlink files in GridFS.
    bucket = _bucket()
    reports = await db.reports.find(
        {"user_id": user.user_id, "attachment_id": {"$ne": None}},
        {"attachment_id": 1},
    ).to_list(length=10_000)
    for r in reports:
        try:
            await bucket.delete(ObjectId(r["attachment_id"]))
        except Exception:
            pass    # missing/corrupt attachment shouldn't block the wipe

    # 2) Delete all per-user documents.
    deleted = {}
    for col in USER_COLLECTIONS:
        res = await db[col].delete_many({"user_id": user.user_id})
        deleted[col] = res.deleted_count

    # 3) Finally remove the user row itself.
    await db.users.delete_one({"user_id": user.user_id})

    return {"ok": True, "deleted_counts": deleted}
