"""
TaskWorkingGroup model — junction table for multi-group task assignment.
Each task can be assigned to multiple working groups.
"""
from sqlalchemy import Column, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class TaskWorkingGroup(Base):
    __tablename__ = "task_working_groups"
    __table_args__ = (
        UniqueConstraint("task_id", "group_id", name="uq_task_working_group"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(Integer, ForeignKey("working_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
