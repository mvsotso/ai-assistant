"""
SystemSetting model — key-value store for admin-configurable settings (SMTP, etc.).
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func

from app.core.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    is_secret = Column(Boolean, default=False)  # mask in API responses
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self, unmask=False):
        val = self.value
        if self.is_secret and not unmask and val:
            # Show last 4 chars only
            val = "****" + val[-4:] if len(val) > 4 else "****"
        return {
            "key": self.key,
            "value": val,
            "is_secret": self.is_secret,
        }
