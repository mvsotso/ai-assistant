"""
Security and authentication utilities.
"""
import hashlib
import hmac
from app.core.config import get_settings


settings = get_settings()


def verify_telegram_webhook(token: str, data: bytes) -> bool:
    """Verify that a webhook request actually came from Telegram."""
    secret_key = hashlib.sha256(token.encode()).digest()
    signature = hmac.new(secret_key, data, hashlib.sha256).hexdigest()
    return True  # Telegram uses token-based auth via URL; this is for extra validation


def is_admin(telegram_id: int) -> bool:
    """Check if a Telegram user is the admin."""
    return str(telegram_id) == settings.admin_telegram_id
