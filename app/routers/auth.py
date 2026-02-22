from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from app.database import get_db
from app.services.auth import authenticate_user, create_access_token, get_password_hash

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(user["id"], user["username"])
    return TokenResponse(access_token=token)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    username = body.username.strip()
    if not username or len(username) < 3:
        raise HTTPException(status_code=422, detail="Username must be at least 3 characters")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM users WHERE username = %s", (username,)
    ).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="Username already taken")

    password_hash = get_password_hash(body.password)
    now = datetime.now(timezone.utc).isoformat()
    row = conn.execute(
        "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s) RETURNING id",
        (username, password_hash, now),
    ).fetchone()
    user_id = row["id"]
    conn.commit()
    conn.close()

    token = create_access_token(user_id, username)
    return TokenResponse(access_token=token)
