"""
TaskAssignee model — junction table for multi-assignee task support.
Each task can have multiple assignees with roles: lead, contributor, reviewer.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class TaskAssignee(Base):
    __tablename__ = "task_assignees"
    __table_args__ = (
        UniqueConstraint("task_id", "user_id", name="uq_task_assignee"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), default="contributor")  # lead / contributor / reviewer
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(255), nullable=True)
