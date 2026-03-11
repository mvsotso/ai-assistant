"""
Collaboration models - task watchers and activity log.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class TaskWatcher(Base):
    __tablename__ = "task_watchers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    user_email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("task_id", "user_email", name="uq_task_watcher"),
    )

    def __repr__(self):
        return f"<TaskWatcher(task_id={self.task_id}, user={self.user_email})>"


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False)  # task, comment, file
    entity_id = Column(Integer, nullable=True)
    action = Column(String(50), nullable=False)  # created, updated, commented, assigned, status_changed
    user_email = Column(String(255), nullable=True)
    details_json = Column(Text, nullable=True)  # JSON with additional details
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ActivityLog(id={self.id}, {self.entity_type}:{self.entity_id} {self.action})>"
