"""
Task model — collaborative task management with assignments.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class TaskStatus(str, enum.Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.TODO, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.MEDIUM, nullable=False)
    label = Column(String(100), nullable=True)
    category = Column(String(100), nullable=True)      # e.g., "GDT", "Kado24", "Personal"
    subcategory = Column(String(100), nullable=True)    # e.g., "ETL", "Frontend", "Learning"

    # Task Group hierarchy
    group_id = Column(Integer, ForeignKey("task_groups.id", ondelete="SET NULL"), nullable=True)
    subgroup_id = Column(Integer, ForeignKey("task_subgroups.id", ondelete="SET NULL"), nullable=True)

    # Creator and assignee (Telegram IDs)
    creator_id = Column(BigInteger, nullable=False)
    creator_name = Column(String(255), nullable=True)
    assignee_id = Column(BigInteger, nullable=True)
    assignee_name = Column(String(255), nullable=True)

    # Source context
    source_chat_id = Column(BigInteger, nullable=True)
    source_message_id = Column(BigInteger, nullable=True)

    due_date = Column(DateTime(timezone=True), nullable=True)
    estimated_hours = Column(Float, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    version = Column(Integer, default=1)
    last_modified_by = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<Task(id={self.id}, title={self.title[:30]}, status={self.status})>"
