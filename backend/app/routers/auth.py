"""Auth endpoints. /login, /me, /status — none of these require a token."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..auth import auth_enabled, check_password, issue_token, require_auth


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    password: str = ""


@router.get("/status")
def auth_status():
    """Lets the frontend learn whether to show the login screen at all."""
    return {"auth_required": auth_enabled()}


@router.post("/login")
def login(body: LoginIn):
    if not auth_enabled():
        # Dev mode: anyone can grab a token. Still issue one for symmetry
        # with prod so the frontend code path is identical.
        return {"token": issue_token(), "auth_required": False}
    if not check_password(body.password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "incorrect password")
    return {"token": issue_token(), "auth_required": True}


@router.get("/me")
def me(user=Depends(require_auth)):
    return {"subject": user.get("sub", "user"), "exp": user.get("exp")}
