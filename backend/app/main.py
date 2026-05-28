from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import ensure_indexes
from .routers import auth, chat, consensus, dashboard, dev, ingest, me, suggestions


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await ensure_indexes()
    except Exception as exc:
        print(f"[startup] index creation skipped: {exc}")
    yield


app = FastAPI(title="Folio", version="0.2.0", lifespan=lifespan)

_origins = [o.strip() for o in (settings.cors_origins or "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=r"https://.*\.vercel\.app" if "*" not in _origins else None,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/auth/* (register, login, status) is unauthenticated.
# Every other router declares Depends(require_auth) on each endpoint
# so they can read the current user and scope queries.
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(ingest.router)
app.include_router(consensus.router)
app.include_router(dashboard.router)
app.include_router(suggestions.router)
app.include_router(dev.router)
app.include_router(me.router)


@app.get("/")
def root():
    return {"service": "folio", "status": "ok", "allow_signup": settings.allow_signup}
