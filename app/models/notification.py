"""
Notification Model — in-app notification center.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(BigInteger, index=True)
    type = Column(String(50), nullable=False)  # task_assigned, task_status, task_overdue, reminder_due, comment_added, ai_insight
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=True)
    link = Column(String(500), nullable=True)
    entity_id = Column(Integer, nullable=True)
    entity_type = Column(String(50), nullable=True)  # task, event, reminder
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "link": self.link,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
