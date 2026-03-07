"""
Task Dependency model — linking tasks with blocks/blocked-by relationships.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class TaskDependency(Base):
    __tablename__ = "task_dependencies"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # The task that is blocked (cannot proceed until dependency is done)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # The task that blocks it (must be completed first)
    depends_on_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)

    # Dependency type: 'blocks' means depends_on blocks task_id
    dep_type = Column(String(20), default="blocks", nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id", name="uq_task_dependency"),
    )

    def __repr__(self):
        return f"<TaskDependency(task={self.task_id} depends_on={self.depends_on_id})>"
