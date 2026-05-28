"""Auth endpoints. /register, /login, /me, /status, /forgot, /reset."""
import hashlib
import os
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import (
    create_user,
    find_user_by_username,
    hash_password,
    issue_token,
    require_auth,
    verify_password,
)
from ..config import settings
from ..db import get_db
from ..email import send_email
from ..schemas import UserPublic


router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=40)
    password: str = Field(..., min_length=6)
    display_name: str = ""
    email: str = ""    # optional, used only for password reset


class LoginIn(BaseModel):
    username: str
    password: str


class AuthOut(BaseModel):
    token: str
    user: UserPublic


@router.get("/status")
def auth_status():
    return {"allow_signup": settings.allow_signup}


@router.post("/register", response_model=AuthOut)
async def register(body: RegisterIn):
    if not settings.allow_signup:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "signup is disabled on this instance")
    user = await create_user(body.username, body.password, body.display_name, email=body.email)
    token = issue_token(user.user_id, user.username)
    return AuthOut(token=token, user=user)


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn):
    user = await find_user_by_username(body.username)
    if not user or not verify_password(body.password, user.password_hash):
        # Same error for both cases so we don't leak which usernames exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect username or password")
    public = UserPublic(user_id=user.user_id, username=user.username, display_name=user.display_name)
    return AuthOut(token=issue_token(user.user_id, user.username), user=public)


@router.get("/me", response_model=UserPublic)
async def me(user: UserPublic = Depends(require_auth)):
    return user


# ─── Password reset ─────────────────────────────────────────────────────
# Two-step flow:
#   1. POST /forgot {username}   → emails a single-use reset URL.
#   2. POST /reset {token, new}  → verifies token + hash, sets new password.
#
# The token is a 32-byte URL-safe string. We store ONLY its SHA-256 hash
# alongside the user_id and expiry — so even a DB read can't recover an
# unused token. Tokens are single-use (deleted on successful reset).
#
# The /forgot endpoint always responds 200 regardless of whether the
# username/email is on file — we don't want to be a user-existence oracle.

_RESET_TTL_S = 30 * 60     # 30 minutes


class ForgotIn(BaseModel):
    username: str


class ResetIn(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _reset_link(token: str) -> str:
    """Build the user-facing reset URL. APP_URL env var controls the host;
    defaults to production. Path is the /reset route in the frontend."""
    base = os.environ.get("APP_URL", "https://folio-health.vercel.app").rstrip("/")
    return f"{base}/reset?token={token}"


@router.post("/forgot")
async def forgot_password(body: ForgotIn):
    """Issue a password-reset token. Always returns ok, even when the user
    doesn't exist, so this endpoint can't be used to enumerate accounts."""
    username = body.username.strip().lower()
    db = get_db()
    user_doc = await db.users.find_one({"username": username})

    if user_doc and (user_doc.get("email") or "").strip():
        token = secrets.token_urlsafe(32)
        await db.password_resets.insert_one({
            "user_id":      user_doc["user_id"],
            "token_hash":   _token_hash(token),
            "created_at":   datetime.now(timezone.utc),
            "expires_at":   datetime.fromtimestamp(time.time() + _RESET_TTL_S, tz=timezone.utc),
            "used":         False,
        })
        link = _reset_link(token)
        await send_email(
            to=user_doc["email"],
            subject="Reset your Folio password",
            body_html=(
                f"<p>Hi {user_doc.get('display_name') or username},</p>"
                f"<p>Use the link below to set a new password for your Folio account. "
                f"It expires in 30 minutes.</p>"
                f"<p><a href=\"{link}\">{link}</a></p>"
                f"<p>If you didn't ask for this, you can ignore this email — your "
                f"current password still works.</p>"
            ),
            body_text=(
                f"Hi {user_doc.get('display_name') or username},\n\n"
                f"Reset your Folio password here (expires in 30 minutes):\n{link}\n\n"
                f"If you didn't ask for this, you can ignore this email."
            ),
        )
    # Either way: don't leak existence.
    return {"ok": True}


@router.post("/reset")
async def reset_password(body: ResetIn):
    """Consume a reset token, set a new password. Token is single-use."""
    db = get_db()
    h = _token_hash(body.token)
    rec = await db.password_resets.find_one({"token_hash": h, "used": False})
    if not rec:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this reset link is invalid or has already been used")

    # Expiry check.
    exp = rec.get("expires_at")
    if not exp:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this reset link is invalid")
    if isinstance(exp, datetime):
        now = datetime.now(timezone.utc)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < now:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "this reset link has expired — request a new one")

    # Apply the new password and mark the token used.
    await db.users.update_one(
        {"user_id": rec["user_id"]},
        {"$set": {"password_hash": hash_password(body.new_password)}},
    )
    await db.password_resets.update_one(
        {"_id": rec["_id"]}, {"$set": {"used": True}},
    )
    # Invalidate every other unused token for the same user (defence in depth).
    await db.password_resets.update_many(
        {"user_id": rec["user_id"], "used": False},
        {"$set": {"used": True}},
    )
    return {"ok": True}
