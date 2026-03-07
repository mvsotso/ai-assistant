"""
Task Action model — checklist items within a task.
Each task can have multiple ordered actions that can be tracked individually.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, BigInteger
from sqlalchemy.sql import func
from app.core.database import Base


class TaskAction(Base):
    __tablename__ = "task_actions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    is_done = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    # Assignee
    assignee_name = Column(String(255), nullable=True)
    assignee_id = Column(BigInteger, nullable=True)

    # Due date
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "is_done": self.is_done,
            "sort_order": self.sort_order,
            "assignee_name": self.assignee_name,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
