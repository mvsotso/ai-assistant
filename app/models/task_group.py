"""
Task Group & Sub Group Models
Hierarchical task categorization: Group → SubGroup → Tasks
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class TaskGroup(Base):
    __tablename__ = "task_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(10), nullable=True)          # Emoji icon for the tab
    color = Column(String(7), nullable=True)           # Hex color for the tab accent
    sort_order = Column(Integer, default=0)            # Tab display order
    is_active = Column(Boolean, default=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subgroups = relationship("TaskSubGroup", back_populates="group", cascade="all, delete-orphan",
                             order_by="TaskSubGroup.sort_order")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "subgroups": [sg.to_dict() for sg in self.subgroups] if self.subgroups else []
        }


class TaskSubGroup(Base):
    __tablename__ = "task_subgroups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    group_id = Column(Integer, ForeignKey("task_groups.id", ondelete="CASCADE"), nullable=False)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    group = relationship("TaskGroup", back_populates="subgroups")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "group_id": self.group_id,
            "sort_order": self.sort_order,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
