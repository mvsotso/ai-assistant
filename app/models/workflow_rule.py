"""
WorkflowRule model - automation rules for task workflows.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class WorkflowRule(Base):
    __tablename__ = "workflow_rules"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    trigger = Column(String(50), nullable=False)  # task_created, task_overdue, status_changed, priority_changed
    condition_json = Column(Text, nullable=True)  # JSON: {"priority": "urgent", "category": "IT"}
    action_type = Column(String(50), nullable=False)  # auto_assign, set_deadline, escalate, notify, change_status
    action_config_json = Column(Text, nullable=True)  # JSON: {"assignee": "Dara", "notify_via": "telegram"}
    is_active = Column(Boolean, default=True)
    creator_email = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<WorkflowRule(id={self.id}, name={self.name}, trigger={self.trigger})>"
