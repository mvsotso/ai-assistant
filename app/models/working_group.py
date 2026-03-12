"""
Working Group models — dedicated team groupings for task assignment.
Separate from TaskGroups which are for task categorization.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.sql import func
from app.core.database import Base


class WorkingGroup(Base):
    __tablename__ = "working_groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String(32), default="👥")
    color = Column(String(7), default="#3b82f6")
    creator_email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WorkingGroupMember(Base):
    __tablename__ = "working_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_wg_member"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    group_id = Column(Integer, ForeignKey("working_groups.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), default="member")  # leader / member
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
