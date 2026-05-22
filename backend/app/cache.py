import hashlib
import json
from typing import Any

import redis.asyncio as redis

from .config import settings

_redis: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def cache_key(*parts: str) -> str:
    h = hashlib.sha256("||".join(parts).encode()).hexdigest()[:32]
    return f"medchat:{h}"


async def get_json(key: str) -> Any | None:
    try:
        raw = await get_redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


async def set_json(key: str, value: Any, ttl: int | None = None) -> None:
    try:
        await get_redis().set(key, json.dumps(value), ex=ttl or settings.cache_ttl_s)
    except Exception:
        pass
