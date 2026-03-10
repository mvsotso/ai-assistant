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

    # Also send web push notification (best-effort)
    try:
        from app.core.config import get_settings
        settings = get_settings()
        admin_email = settings.dashboard_allowed_emails.split(",")[0].strip()
        await send_push_notification(db, admin_email, title, message or "")
    except Exception:
        pass  # Push is best-effort, don't break notification creation

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


def _get_vapid_pem(raw_b64_key: str) -> str:
    """Convert raw base64url-encoded private key to PEM format for pywebpush."""
    import base64
    # Add padding if needed
    padding = '=' * (4 - len(raw_b64_key) % 4) if len(raw_b64_key) % 4 else ''
    key_bytes = base64.urlsafe_b64decode(raw_b64_key + padding)

    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    # Reconstruct EC private key from raw 32-byte value
    private_value = int.from_bytes(key_bytes, 'big')
    private_key = ec.derive_private_key(private_value, ec.SECP256R1())
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    return pem


async def send_push_notification(db: AsyncSession, user_email: str, title: str, body: str, url: str = None):
    """Send web push notification to all subscriptions for a user."""
    import json
    from app.core.config import get_settings
    from app.models.push_subscription import PushSubscription

    settings = get_settings()
    if not settings.vapid_private_key:
        return  # Push not configured

    result = await db.execute(
        select(PushSubscription).where(PushSubscription.user_email == user_email)
    )
    subs = list(result.scalars().all())
    if not subs:
        return

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush not installed, skipping push")
        return

    # Convert raw base64url key to PEM if needed
    priv_key = settings.vapid_private_key
    if not priv_key.startswith("-----"):
        try:
            priv_key = _get_vapid_pem(priv_key)
        except Exception as e:
            logger.error(f"Failed to convert VAPID key: {e}")
            return

    payload = json.dumps({"title": title, "body": body, "url": url or "/"})

    for sub in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": {"p256dh": sub.p256dh, "auth": sub.auth}
                },
                data=payload,
                vapid_private_key=priv_key,
                vapid_claims={"sub": settings.vapid_email}
            )
        except WebPushException as e:
            error_str = str(e)
            if "410" in error_str or "404" in error_str:
                # Subscription expired, remove it
                await db.delete(sub)
                logger.info(f"Removed expired push subscription {sub.id}")
            else:
                logger.error(f"Push notification failed for sub {sub.id}: {e}")
        except Exception as e:
            logger.error(f"Push send error: {e}")
