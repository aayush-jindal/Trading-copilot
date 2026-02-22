from fastapi import APIRouter, Header, HTTPException, status

from app.config import INTERNAL_SECRET
from app.services.digest import run_nightly_refresh

router = APIRouter(prefix="/internal", tags=["internal"])


def _verify_internal(authorization: str | None = Header(default=None)) -> None:
    if not INTERNAL_SECRET:
        raise HTTPException(status_code=503, detail="INTERNAL_SECRET not configured")
    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:]
    if token != INTERNAL_SECRET:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal token")


@router.post("/refresh-watchlist")
def refresh_watchlist(authorization: str | None = Header(default=None)):
    _verify_internal(authorization)
    result = run_nightly_refresh()
    return result
