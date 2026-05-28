"""
Retry helpers for LLM and HTTP calls.

LLM provider APIs return 429 (rate limit), 503 (overloaded), and the occasional
network blip. A real medical app talking to your mom can't show a hard error
on the first transient failure — it should retry quietly a couple of times
before bubbling up. This module is the one place that knows what "transient"
means so every call site uses the same policy.

Usage:
    from .retry import with_retries, is_transient

    result = await with_retries(
        lambda: client.messages.create(model=..., messages=[...]),
        attempts=3,
    )

The wrapped callable must be an async-callable that takes no arguments — use
a lambda or functools.partial to bind your call.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)


# HTTP statuses we should retry on. 408/425/429/5xx are the conventional set;
# we exclude 501 (not implemented — a real bug) and 505/511 which won't
# benefit from a retry. 524 covers Cloudflare timeouts.
_TRANSIENT_STATUSES = {408, 425, 429, 500, 502, 503, 504, 524, 529}


def is_transient(exc: BaseException) -> bool:
    """True if `exc` looks like something that retrying might fix.

    Covers: provider 429/5xx, network resets, DNS hiccups, asyncio timeouts.
    Does NOT cover: auth errors (401/403), missing model (404),
    malformed-request (400) — those will only fail again.
    """
    # asyncio.TimeoutError / built-in TimeoutError
    if isinstance(exc, asyncio.TimeoutError) or isinstance(exc, TimeoutError):
        return True

    # Connection/read errors from httpx underlying the SDKs
    name = exc.__class__.__name__
    if name in {"ConnectError", "ConnectTimeout", "ReadTimeout",
                "WriteTimeout", "PoolTimeout", "RemoteProtocolError",
                "ReadError", "WriteError", "NetworkError"}:
        return True

    # Anthropic / OpenAI SDK errors expose a .status_code attribute
    code = getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _TRANSIENT_STATUSES:
        return True

    # Some SDKs put it under .response.status_code
    resp = getattr(exc, "response", None)
    if resp is not None:
        code = getattr(resp, "status_code", None) or getattr(resp, "status", None)
        if isinstance(code, int) and code in _TRANSIENT_STATUSES:
            return True

    # google-generativeai raises ResourceExhausted (429), InternalServerError
    # (500), ServiceUnavailable (503) from google.api_core.exceptions.
    if name in {"ResourceExhausted", "InternalServerError", "ServiceUnavailable",
                "DeadlineExceeded", "Aborted", "Unavailable"}:
        return True

    return False


async def with_retries(
    call: Callable[[], Awaitable[Any]],
    *,
    attempts: int = 3,
    base_ms: int = 300,
    max_ms: int = 4_000,
    jitter: float = 0.25,
    label: str | None = None,
) -> Any:
    """Run `call()` with exponential backoff on transient errors.

    Sleeps ~ base_ms * 2**(attempt-1), capped at max_ms, with ±jitter.
    Re-raises the *last* exception so the caller sees a real traceback.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await call()
        except BaseException as exc:
            if not is_transient(exc) or attempt == attempts:
                raise
            last_exc = exc
            backoff = min(max_ms, base_ms * (2 ** (attempt - 1))) / 1000.0
            backoff *= 1 + random.uniform(-jitter, jitter)
            log.warning("transient error (%s) on %s try %d/%d — retrying in %.2fs",
                        type(exc).__name__, label or call, attempt, attempts, backoff)
            await asyncio.sleep(backoff)
    # Unreachable but type-checkers like it.
    assert last_exc is not None
    raise last_exc
