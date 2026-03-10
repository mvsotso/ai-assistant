"""
Email Preference Model — stores per-user email notification preferences.
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func

from app.core.database import Base


class EmailPreference(Base):
    __tablename__ = "email_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_email = Column(String(255), unique=True, nullable=False, index=True)
    email_enabled = Column(Boolean, default=True)
    task_assigned = Column(Boolean, default=True)
    task_status_change = Column(Boolean, default=True)
    reminder_due = Column(Boolean, default=True)
    daily_summary = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "user_email": self.user_email,
            "email_enabled": self.email_enabled,
            "task_assigned": self.task_assigned,
            "task_status_change": self.task_status_change,
            "reminder_due": self.reminder_due,
            "daily_summary": self.daily_summary,
        }
