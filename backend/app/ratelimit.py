"""
Per-user rate limits backed by Redis.

Two patterns:
1. Sliding-minute limits ("X requests per minute") for chatty endpoints.
2. Daily caps ("Y per day") for expensive endpoints (ingest, consensus).

Limits are intentionally generous for a personal-use app — they exist to
catch runaway clients, bugs, or a stolen token, not to gate normal use.
If Redis is unreachable, we FAIL OPEN (allow the request) — losing rate
limits is better than locking everyone out because Redis blipped.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException

from .cache import get_redis


@dataclass(frozen=True)
class Limit:
    name: str
    per_minute: int = 0       # 0 means no per-minute cap
    per_day: int = 0          # 0 means no per-day cap

    def __post_init__(self):
        if self.per_minute <= 0 and self.per_day <= 0:
            raise ValueError(f"Limit {self.name!r} has no caps set")


# Tuned for a family-sized userbase. Adjust as you grow.
LIMITS: dict[str, Limit] = {
    "chat":      Limit("chat",      per_minute=20, per_day=400),
    "ingest":    Limit("ingest",    per_minute=10, per_day=80),
    "consensus": Limit("consensus", per_minute=4,  per_day=20),
    "vision":    Limit("vision",    per_minute=6,  per_day=40),
}


class RateLimited(HTTPException):
    """429 with a friendly retry-after hint."""
    def __init__(self, kind: str, retry_after: int, kind_label: str = ""):
        super().__init__(
            status_code=429,
            detail={
                "message": f"You've hit the {kind_label or kind} limit for now. "
                           f"Please try again in {retry_after} second{'s' if retry_after != 1 else ''}.",
                "kind": kind,
                "retry_after": retry_after,
            },
            headers={"Retry-After": str(retry_after)},
        )


async def enforce(kind: str, user_id: str) -> None:
    """Atomically increment the counter for (kind, user_id) and raise if over.

    Fails open if Redis is unreachable — we'd rather serve a request than
    503 the whole app.
    """
    limit = LIMITS.get(kind)
    if limit is None:
        return                          # unknown kind → no limit

    try:
        r = get_redis()
        now_minute = int(time.time() // 60)
        now_day = time.strftime("%Y%m%d")

        if limit.per_minute > 0:
            key = f"rl:{kind}:{user_id}:m:{now_minute}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 90)     # window + small buffer
            if count > limit.per_minute:
                # Compute time until the minute rolls over.
                retry_after = 60 - int(time.time() % 60)
                raise RateLimited(kind, max(retry_after, 1),
                                   kind_label=_friendly_label(kind))

        if limit.per_day > 0:
            key = f"rl:{kind}:{user_id}:d:{now_day}"
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, 86_400 + 600)
            if count > limit.per_day:
                # Time until midnight UTC.
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                tomorrow = (now + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0)
                retry_after = int((tomorrow - now).total_seconds())
                raise RateLimited(f"{kind}_daily", retry_after,
                                   kind_label=f"daily {_friendly_label(kind)}")
    except RateLimited:
        raise
    except Exception:
        # Redis unreachable or other internal issue — fail open.
        return


def _friendly_label(kind: str) -> str:
    return {
        "chat":      "chat",
        "ingest":    "report upload",
        "consensus": "high-confidence extraction",
        "vision":    "image analysis",
    }.get(kind, kind)
