"""
Notification API — in-app notification center endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from pydantic import BaseModel
from app.core.database import get_db
from app.core.config import get_settings
from app.models.notification import Notification
from app.models.push_subscription import PushSubscription
from app.services.notification_svc import (
    get_notifications, get_unread_count, mark_read, mark_all_read, create_notification,
    send_push_notification,
)
from app.api.auth import require_auth

notification_router = APIRouter(
    prefix="/api/v1/notifications", tags=["Notifications"],
    dependencies=[Depends(require_auth)],
)

# Public router — no auth required (for service worker VAPID key access)
notification_public_router = APIRouter(
    prefix="/api/v1/notifications", tags=["Notifications"],
)


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



# ── Push Subscription Models ──
class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class PushUnsubscribeRequest(BaseModel):
    endpoint: str


# ── VAPID Public Key (no auth required — needed before login for SW) ──
@notification_public_router.get("/vapid-key")
async def get_vapid_key():
    """Return the VAPID public key for push subscription."""
    settings = get_settings()
    if not settings.vapid_public_key:
        raise HTTPException(status_code=503, detail="Push notifications not configured")
    return {"public_key": settings.vapid_public_key}


@notification_router.post("/subscribe")
async def subscribe_push(
    body: PushSubscribeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Subscribe browser for push notifications."""
    payload = await require_auth(request)
    email = payload.get("email", "")

    # Check if subscription already exists
    existing = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    if existing.scalar_one_or_none():
        return {"ok": True, "message": "Already subscribed"}

    sub = PushSubscription(
        user_email=email,
        endpoint=body.endpoint,
        p256dh=body.p256dh,
        auth=body.auth,
    )
    db.add(sub)
    await db.commit()
    return {"ok": True, "message": "Subscribed for push notifications"}


@notification_router.post("/unsubscribe")
async def unsubscribe_push(
    body: PushUnsubscribeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Unsubscribe browser from push notifications."""
    await require_auth(request)

    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == body.endpoint)
    )
    sub = result.scalar_one_or_none()
    if sub:
        await db.delete(sub)
        await db.commit()
    return {"ok": True, "message": "Unsubscribed"}


@notification_router.post("/test-push")
async def test_push(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a test push notification to the current user."""
    payload = await require_auth(request)
    email = payload.get("email", "")
    await send_push_notification(db, email, "Test Notification", "Push notifications are working!")
    await db.commit()
    return {"ok": True, "message": "Test push sent"}
