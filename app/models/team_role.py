"""
Team Role model — custom roles for team members.
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from app.core.database import Base


class TeamRole(Base):
    __tablename__ = "team_roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    color = Column(String(7), default="#3b82f6")       # Hex color for badge
    permissions = Column(Text, nullable=True)           # JSON string: ["view","edit","admin"]
    is_default = Column(Boolean, default=False)         # Default role for new members
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "color": self.color,
            "permissions": json.loads(self.permissions) if self.permissions else [],
            "is_default": self.is_default,
            "sort_order": self.sort_order,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
