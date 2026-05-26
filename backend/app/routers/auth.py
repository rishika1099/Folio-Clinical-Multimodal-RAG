"""Auth endpoints. /register, /login, /me, /status."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..auth import (
    create_user,
    find_user_by_username,
    issue_token,
    require_auth,
    verify_password,
)
from ..config import settings
from ..schemas import UserPublic


router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=2, max_length=40)
    password: str = Field(..., min_length=6)
    display_name: str = ""


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
    user = await create_user(body.username, body.password, body.display_name)
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
