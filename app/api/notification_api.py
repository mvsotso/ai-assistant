"""
Notification API — in-app notification center endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.models.notification import Notification
from app.services.notification_svc import (
    get_notifications, get_unread_count, mark_read, mark_all_read, create_notification,
)

notification_router = APIRouter(prefix="/api/v1/notifications", tags=["Notifications"])


@notification_router.get("")
async def list_notifications(
    unread_only: bool = False,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Get recent notifications."""
    notifs = await get_notifications(db, unread_only=unread_only, limit=limit)
    return {"notifications": [n.to_dict() for n in notifs]}


@notification_router.get("/count")
async def notification_count(db: AsyncSession = Depends(get_db)):
    """Get unread notification count."""
    count = await get_unread_count(db)
    return {"count": count}


@notification_router.post("/{notif_id}/read")
async def read_notification(notif_id: int, db: AsyncSession = Depends(get_db)):
    """Mark a notification as read."""
    ok = await mark_read(db, notif_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@notification_router.post("/read-all")
async def read_all_notifications(db: AsyncSession = Depends(get_db)):
    """Mark all notifications as read."""
    await mark_all_read(db)
    return {"ok": True}


@notification_router.delete("/{notif_id}")
async def delete_notification(notif_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a notification."""
    result = await db.execute(select(Notification).where(Notification.id == notif_id))
    notif = result.scalar_one_or_none()
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    await db.delete(notif)
    return {"deleted": True}
