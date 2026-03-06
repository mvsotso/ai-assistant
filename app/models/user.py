"""
User model — represents a registered Telegram user.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    timezone = Column(String(50), default="Asia/Phnom_Penh")
    language = Column(String(10), default="en")
    google_token = Column(Text, nullable=True)  # Encrypted JSON of Google OAuth2 credentials
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, name={self.first_name})>"
