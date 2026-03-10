"""
Reminder model — scheduled notifications delivered via Telegram.
Phase 16: Enhanced with snooze, task/event linking, datetime picker.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class Reminder(Base):
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    chat_id = Column(BigInteger, nullable=False)  # Where to send the reminder
    message = Column(Text, nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_sent = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_rule = Column(String(100), nullable=True)  # e.g., "daily", "weekly"
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Phase 16: Task/Event linking
    task_id = Column(Integer, nullable=True)           # Link to tasks.id
    event_id = Column(String(500), nullable=True)      # Google Calendar event ID

    # Phase 16: Snooze tracking
    snooze_count = Column(Integer, default=0)
    original_remind_at = Column(DateTime(timezone=True), nullable=True)  # Before first snooze
    telegram_message_id = Column(BigInteger, nullable=True)  # Track sent msg for keyboard edit

    def __repr__(self):
        return f"<Reminder(id={self.id}, at={self.remind_at}, sent={self.is_sent}, snoozes={self.snooze_count})>"
