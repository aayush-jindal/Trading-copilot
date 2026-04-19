"""FastAPI dependency functions for authentication.

Provides reusable Depends()-compatible callables that validate JWTs,
keeping auth logic out of individual route functions.
"""

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.services.auth import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """FastAPI dependency — validates JWT and returns {id, username}."""
    return decode_token(token)
