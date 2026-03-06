"""
Task model — collaborative task management with assignments.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Enum
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
    label = Column(String(100), nullable=True)  # Phase 3: category label (e.g., "ETL", "Kado24", "GDT")

    # Creator and assignee (Telegram IDs)
    creator_id = Column(BigInteger, nullable=False)
    creator_name = Column(String(255), nullable=True)
    assignee_id = Column(BigInteger, nullable=True)
    assignee_name = Column(String(255), nullable=True)

    # Source context
    source_chat_id = Column(BigInteger, nullable=True)  # Which group chat it came from
    source_message_id = Column(BigInteger, nullable=True)  # Original message ID

    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Task(id={self.id}, title={self.title[:30]}, status={self.status})>"
