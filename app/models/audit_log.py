"""
AuditLog model — tracks changes to tasks for audit trail.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False, index=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(50), nullable=False)  # created, updated, status_changed, deleted
    field_changed = Column(String(100), nullable=True)  # which field changed
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AuditLog(id={self.id}, task={self.task_id}, action={self.action})>"
