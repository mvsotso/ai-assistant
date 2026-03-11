"""
TimeLog model - time tracking entries for tasks.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Float, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class TimeLog(Base):
    __tablename__ = "time_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_email = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_minutes = Column(Float, default=0)
    is_running = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<TimeLog(id={self.id}, task_id={self.task_id}, duration={self.duration_minutes}m)>"
