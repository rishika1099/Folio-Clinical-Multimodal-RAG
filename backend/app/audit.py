"""
Lightweight audit log.

One Mongo collection (`audit_events`) records who-did-what-when on
sensitive actions. Intentionally small schema, no PII beyond user_id, so
the log itself is safe to keep indefinitely.

Schema:
  {
    "_id":        ObjectId,
    "user_id":    str,
    "action":     str,   # e.g. "view_report", "export", "delete_account",
                          #      "chat_query", "consensus_run"
    "target":     str,   # report_id, "self", "all", or a short label
    "ts":         datetime (utc),
    "meta":       dict | None,   # tiny structured extras (counts, model)
  }

A TTL index on `ts` keeps the collection bounded — defaults to 180 days.

Logging is best-effort: if Mongo is unreachable we swallow the exception
rather than failing the user's request. Audit is observability, not the
critical path.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from .db import get_db

_AUDIT_TTL_DAYS = 180
_INDEX_READY = False
_INDEX_LOCK = asyncio.Lock()


async def _ensure_index() -> None:
    global _INDEX_READY
    if _INDEX_READY:
        return
    async with _INDEX_LOCK:
        if _INDEX_READY:
            return
        try:
            db = get_db()
            await db.audit_events.create_index(
                "ts", expireAfterSeconds=_AUDIT_TTL_DAYS * 86_400,
                name="audit_ttl",
            )
            await db.audit_events.create_index(
                [("user_id", 1), ("ts", -1)], name="audit_by_user",
            )
            _INDEX_READY = True
        except Exception:
            # Don't keep trying every call if it failed — leave _INDEX_READY
            # False so a later call retries, but accept that audit may
            # silently degrade if Mongo is broken.
            pass


async def log_event(
    user_id: str,
    action: str,
    target: str = "self",
    meta: dict | None = None,
) -> None:
    """Fire-and-forget log of an audit event. Never raises."""
    try:
        await _ensure_index()
        await get_db().audit_events.insert_one({
            "user_id": user_id,
            "action": action,
            "target": target,
            "ts": datetime.now(timezone.utc),
            "meta": meta or None,
        })
    except Exception:
        pass


async def recent_events(user_id: str, limit: int = 50) -> list[dict]:
    """Most recent audit events for a user, newest first. Used by the
    Profile page's `/api/me/audit` endpoint if you want to surface it."""
    try:
        cursor = get_db().audit_events.find(
            {"user_id": user_id}, {"_id": 0},
        ).sort("ts", -1).limit(limit)
        return await cursor.to_list(length=limit)
    except Exception:
        return []
