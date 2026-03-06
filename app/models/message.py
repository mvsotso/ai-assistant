"""
Message model — stores Telegram messages for summarization and tracking.
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.core.database import Base


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_message_id = Column(BigInteger, nullable=False)
    chat_id = Column(BigInteger, nullable=False, index=True)
    chat_title = Column(String(255), nullable=True)
    sender_id = Column(BigInteger, nullable=False)
    sender_name = Column(String(255), nullable=True)
    text = Column(Text, nullable=True)
    is_command = Column(Boolean, default=False)
    has_task_keyword = Column(Boolean, default=False)  # Contains TODO, ACTION, DEADLINE, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Message(id={self.id}, chat={self.chat_title}, sender={self.sender_name})>"
