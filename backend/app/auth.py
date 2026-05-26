"""
Multi-user auth.

Users register with a username + password. Passwords are stored hashed
(bcrypt via passlib). On login, the password is verified against the
hash and a JWT is issued carrying {sub: user_id, username, exp}.

The `require_auth` dependency decodes the token and returns the current
user record from Mongo. Every protected route in the app uses
`current_user.user_id` to scope its Mongo reads and writes — see
backend/app/db.py for the compound (user_id, …) indexes.
"""
import time

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from .config import settings
from .db import get_db
from .schemas import User, UserPublic


bearer = HTTPBearer(auto_error=False)
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except Exception:
        return False


def issue_token(user_id: str, username: str) -> str:
    now = int(time.time())
    payload = {
        "sub": user_id,
        "username": username,
        "iat": now,
        "exp": now + settings.jwt_ttl_days * 86400,
    }
    return pyjwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> dict:
    try:
        return pyjwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")


async def require_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UserPublic:
    """FastAPI dep. Decodes the JWT and looks up the user in Mongo.
    Returns a UserPublic (never the hashed password)."""
    if not creds or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "authentication required")
    payload = _decode_token(creds.credentials)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    db = get_db()
    doc = await db.users.find_one({"user_id": user_id}, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user no longer exists")
    return UserPublic(**doc)


async def find_user_by_username(username: str) -> User | None:
    db = get_db()
    doc = await db.users.find_one({"username": username.lower()}, {"_id": 0})
    return User(**doc) if doc else None


async def create_user(username: str, password: str, display_name: str = "") -> UserPublic:
    """Insert a new user. Raises HTTPException(409) if username is taken."""
    if not username or not password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username and password required")
    if len(password) < 6:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "password must be at least 6 characters")
    username = username.strip().lower()
    if len(username) < 2 or len(username) > 40:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username must be 2–40 characters")
    if not all(c.isalnum() or c in "_-." for c in username):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "username may use letters, numbers, _, -, .")
    if await find_user_by_username(username):
        raise HTTPException(status.HTTP_409_CONFLICT, "username already taken")

    user = User(
        username=username,
        display_name=(display_name or username).strip(),
        password_hash=hash_password(password),
    )
    db = get_db()
    await db.users.insert_one(user.model_dump())
    return UserPublic(user_id=user.user_id, username=user.username, display_name=user.display_name)
