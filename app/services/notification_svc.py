"""
Notification Service — create and query notifications.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc, update

from app.models.notification import Notification

logger = logging.getLogger(__name__)


async def create_notification(
    db: AsyncSession,
    user_id: int,
    notif_type: str,
    title: str,
    message: str = None,
    entity_id: int = None,
    entity_type: str = None,
    link: str = None,
) -> Notification:
    """Create an in-app notification."""
    notif = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        message=message,
        entity_id=entity_id,
        entity_type=entity_type,
        link=link,
    )
    db.add(notif)
    await db.flush()
    return notif


async def get_notifications(db: AsyncSession, user_id: int = None, unread_only: bool = False, limit: int = 30):
    """Get notifications, optionally filtered."""
    query = select(Notification).order_by(Notification.created_at.desc()).limit(limit)
    if user_id:
        query = query.where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.is_read == False)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_unread_count(db: AsyncSession, user_id: int = None) -> int:
    """Get count of unread notifications."""
    query = select(sqlfunc.count(Notification.id)).where(Notification.is_read == False)
    if user_id:
        query = query.where(Notification.user_id == user_id)
    result = await db.execute(query)
    return result.scalar() or 0


async def mark_read(db: AsyncSession, notif_id: int) -> bool:
    """Mark a single notification as read."""
    result = await db.execute(select(Notification).where(Notification.id == notif_id))
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = True
        return True
    return False


async def mark_all_read(db: AsyncSession, user_id: int = None):
    """Mark all notifications as read."""
    stmt = update(Notification).where(Notification.is_read == False).values(is_read=True)
    if user_id:
        stmt = stmt.where(Notification.user_id == user_id)
    await db.execute(stmt)
