from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


class Notification(BaseModel):
    id: int
    content: dict
    created_at: str
    is_read: bool


@router.get("", response_model=list[Notification])
def get_notifications(user: dict = Depends(get_current_user)):
    conn = get_db()
    rows = conn.execute(
        """SELECT id, content, created_at, is_read
           FROM notifications WHERE user_id = %s
           ORDER BY created_at DESC LIMIT 50""",
        (user["id"],),
    ).fetchall()
    conn.close()
    import json
    return [
        Notification(
            id=r["id"],
            content=json.loads(r["content"]),
            created_at=r["created_at"],
            is_read=bool(r["is_read"]),
        )
        for r in rows
    ]


@router.patch("/{notification_id}/read")
def mark_read(notification_id: int, user: dict = Depends(get_current_user)):
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
    conn = get_db()
    conn.execute(
        "UPDATE notifications SET is_read = TRUE WHERE user_id = %s",
        (user["id"],),
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
