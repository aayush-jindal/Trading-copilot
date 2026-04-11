"""Notification endpoints.

Nightly digest results and trade alerts are stored as notifications.

GET    /notifications             — list the 50 most recent for current user
PATCH  /notifications/{id}/read  — mark a single notification as read
PATCH  /notifications/read-all   — mark all notifications as read
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class Notification(BaseModel):
    id: int
    type: str = "digest"
    content: dict
    created_at: str
    is_read: bool


@router.get("", response_model=list[Notification])
def get_notifications(user: dict = Depends(get_current_user)):
    """Return the 50 most recent notifications for the authenticated user."""
    conn = get_db()
    rows = conn.execute(
        """SELECT id, type, content, created_at, is_read
           FROM notifications WHERE user_id = %s
           ORDER BY created_at DESC LIMIT 50""",
        (user["id"],),
    ).fetchall()
    conn.close()
    import json
    return [
        Notification(
            id=r["id"],
            type=r["type"] or "digest",
            content=json.loads(r["content"]),
            created_at=r["created_at"],
            is_read=bool(r["is_read"]),
        )
        for r in rows
    ]


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, user: dict = Depends(get_current_user)):
    """Mark a single notification as read (scoped to current user)."""
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = TRUE WHERE id = %s AND user_id = %s",
        (notification_id, user["id"]),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}


@router.patch("/read-all")
def mark_all_read(user: dict = Depends(get_current_user)):
    """Mark all notifications as read for the current user."""
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = TRUE WHERE user_id = %s",
        (user["id"],),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
