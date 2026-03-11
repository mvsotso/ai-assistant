"""
TaskTemplate model — reusable presets for quick task creation.
"""
import json
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    description_text = Column(Text, nullable=True)
    icon = Column(String(10), default="📋")
    color = Column(String(7), default="#3b82f6")

    # Task field defaults
    title_template = Column(String(500), nullable=False)
    priority = Column(String(50), default="medium")
    status = Column(String(50), default="todo")
    category = Column(String(100), nullable=True)
    subcategory = Column(String(100), nullable=True)
    assignee_name = Column(String(255), nullable=True)
    label = Column(String(100), nullable=True)
    due_offset_hours = Column(Integer, nullable=True)
    group_id = Column(Integer, nullable=True)
    subgroup_id = Column(Integer, nullable=True)

    # Checklist items as JSON: [{"title":"...", "assignee_name":"..."}]
    checklist_json = Column(Text, nullable=True)

    # Meta
    is_builtin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    use_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        checklist = []
        if self.checklist_json:
            try:
                checklist = json.loads(self.checklist_json)
            except (json.JSONDecodeError, TypeError):
                pass
        return {
            "id": self.id,
            "name": self.name,
            "description_text": self.description_text,
            "icon": self.icon,
            "color": self.color,
            "title_template": self.title_template,
            "priority": self.priority,
            "status": self.status,
            "category": self.category,
            "subcategory": self.subcategory,
            "assignee_name": self.assignee_name,
            "label": self.label,
            "due_offset_hours": self.due_offset_hours,
            "group_id": self.group_id,
            "subgroup_id": self.subgroup_id,
            "checklist": checklist,
            "is_builtin": self.is_builtin,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "use_count": self.use_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
