from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import require_auth
from .config import settings
from .db import ensure_indexes
from .routers import auth, chat, consensus, dashboard, dev, ingest, suggestions


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

# /api/auth/* is intentionally NOT protected so /login can be called by an
# unauthenticated browser. Everything else requires the bearer token.
app.include_router(auth.router)

protected = [Depends(require_auth)]
app.include_router(chat.router,        dependencies=protected)
app.include_router(ingest.router,      dependencies=protected)
app.include_router(consensus.router,   dependencies=protected)
app.include_router(dashboard.router,   dependencies=protected)
app.include_router(suggestions.router, dependencies=protected)
app.include_router(dev.router,         dependencies=protected)


@app.get("/")
def root():
    return {"service": "folio", "status": "ok", "auth_required": bool(settings.app_password)}
