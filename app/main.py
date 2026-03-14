import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.dependencies import get_current_user
from app.routers import analysis, auth, data, internal, notifications, options, synthesis, watchlist


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Trading Copilot", lifespan=lifespan)

# CORS — allow local dev + production frontend (set FRONTEND_URL in env for prod)
_origins = ["http://localhost:5173"]
if os.getenv("FRONTEND_URL"):
    _origins.append(os.environ["FRONTEND_URL"])

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["GET", "POST", "DELETE", "PATCH", "PUT"],
    allow_headers=["*"],
)

# ── Public routes ─────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(internal.router)

# ── Protected routes (require JWT) ────────────────────────────────────────────
_auth = {"dependencies": [Depends(get_current_user)]}
app.include_router(data.router,          **_auth)
app.include_router(analysis.router,      **_auth)
app.include_router(synthesis.router,     **_auth)
app.include_router(watchlist.router,     **_auth)
app.include_router(notifications.router, **_auth)
app.include_router(options.router,       **_auth)


@app.get("/health")
def health():
    return {"status": "ok"}
