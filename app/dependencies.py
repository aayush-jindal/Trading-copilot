from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.services.auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — validates JWT and returns {id, username}."""
    return decode_token(token)


def require_internal_token(authorization: str | None = None) -> None:
    """Dependency for internal endpoints protected by INTERNAL_SECRET."""
    from fastapi.security.utils import get_authorization_scheme_param
    from app.config import INTERNAL_SECRET

    if not INTERNAL_SECRET:
        raise HTTPException(status_code=503, detail="Internal secret not configured")

    scheme, token = get_authorization_scheme_param(authorization or "")
    if scheme.lower() != "bearer" or token != INTERNAL_SECRET:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal token",
        )
