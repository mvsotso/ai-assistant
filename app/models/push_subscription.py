"""
Push Subscription Model — stores browser push notification subscriptions.
"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), index=True, nullable=False)
    endpoint = Column(String(2000), unique=True, nullable=False)
    p256dh = Column(String(200), nullable=False)
    auth = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_email": self.user_email,
            "endpoint": self.endpoint[:50] + "...",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
