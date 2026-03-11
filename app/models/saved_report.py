"""
SavedReport model - saved report configurations with scheduling.
"""
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from app.core.database import Base


class SavedReport(Base):
    __tablename__ = "saved_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    report_type = Column(String(50), nullable=False, default="status_summary")
    # status_summary, team_workload, completion_trend, category_breakdown, custom
    filters_json = Column(Text, nullable=True)  # JSON: date_range, category, assignee, group
    schedule = Column(String(20), default="none")  # none, daily, weekly, monthly
    recipients_json = Column(Text, nullable=True)  # JSON: list of email addresses
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    creator_email = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SavedReport(id={self.id}, name={self.name}, type={self.report_type})>"
