"""
TaskFile model - file attachments for tasks.
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, BigInteger, ForeignKey
from sqlalchemy.sql import func
from app.core.database import Base


class TaskFile(Base):
    __tablename__ = "task_files"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    filename = Column(String(500), nullable=False)  # stored filename (uuid_original)
    original_filename = Column(String(500), nullable=False)
    file_size = Column(BigInteger, default=0)
    mime_type = Column(String(200), nullable=True)
    storage_path = Column(String(1000), nullable=False)
    uploader_email = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    ai_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<TaskFile(id={self.id}, filename={self.original_filename})>"
