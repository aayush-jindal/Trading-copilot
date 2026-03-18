"""Authentication service.

Handles password hashing/verification (bcrypt), JWT creation and decoding
(python-jose), and the database lookup that validates login credentials.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, status
from jose import JWTError, jwt

from app.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY
from app.database import get_db


def get_password_hash(password: str) -> str:
    """Return a bcrypt hash of the given plaintext password."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if the plaintext password matches the stored bcrypt hash."""
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def authenticate_user(username: str, password: str) -> dict | None:
    """Look up username in DB and verify password.

    Returns {id, username} dict on success, None if credentials are wrong.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT id, username, password_hash FROM users WHERE username = %s", (username,)
    ).fetchone()
    conn.close()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"]}


def create_access_token(user_id: int, username: str) -> str:
    """Create a signed JWT for the given user, valid for JWT_EXPIRE_MINUTES."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "username": username, "exp": expire}
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT, returning {id, username}.

    Raises HTTP 401 if the token is missing, expired, or tampered with.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        user_id: str | None = payload.get("sub")
        username: str | None = payload.get("username")
        if user_id is None or username is None:
            raise credentials_exception
        return {"id": int(user_id), "username": username}
    except JWTError:
        raise credentials_exception
