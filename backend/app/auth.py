"""
Single-user JWT auth.

Design:
- If FOLIO_APP_PASSWORD is unset → auth is OFF. Convenient for local dev.
- If set → every protected endpoint requires `Authorization: Bearer <jwt>`
  obtained from /api/auth/login. The login endpoint constant-time compares
  the supplied password to FOLIO_APP_PASSWORD.

Single-user-only: there is exactly one principal (subject="user"). Adding
multi-user later means partitioning every Mongo collection by user_id and
issuing per-user tokens — straightforward but out of scope here.
"""
import secrets
import time

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings


bearer = HTTPBearer(auto_error=False)


def auth_enabled() -> bool:
    return bool(settings.app_password)


def issue_token(subject: str = "user") -> str:
    now = int(time.time())
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.jwt_ttl_days * 86400,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


def check_password(supplied: str) -> bool:
    if not settings.app_password:
        return True
    return secrets.compare_digest(supplied or "", settings.app_password)


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """FastAPI dependency. Returns the decoded JWT payload (or a stub
    when auth is disabled in dev)."""
    if not auth_enabled():
        return {"sub": "anonymous", "auth_disabled": True}
    if not creds or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    return verify_token(creds.credentials)
