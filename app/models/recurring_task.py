"""
RecurringTask model — templates for tasks that repeat on a schedule.
Schedules: daily, weekly, monthly, quarterly, semi_annually, yearly
"""
from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Enum, Boolean
from sqlalchemy.sql import func
from app.core.database import Base
import enum


class RecurrenceType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    SEMI_ANNUALLY = "semi_annually"
    YEARLY = "yearly"


class RecurringTask(Base):
    __tablename__ = "recurring_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(String(50), default="medium")
    category = Column(String(100), nullable=True)
    subcategory = Column(String(100), nullable=True)
    assignee_name = Column(String(255), nullable=True)

    # Recurrence settings
    recurrence = Column(Enum(RecurrenceType), nullable=False)
    day_of_week = Column(Integer, nullable=True)       # 0=Mon, 6=Sun (for weekly)
    day_of_month = Column(Integer, nullable=True)       # 1-31 (for monthly/quarterly/semi/yearly)
    month_of_year = Column(Integer, nullable=True)      # 1-12 (for yearly)
    quarter_months = Column(String(50), nullable=True)  # e.g. "1,4,7,10" (for quarterly)
    semi_months = Column(String(50), nullable=True)     # e.g. "1,7" (for semi-annually)
    time_of_day = Column(String(10), nullable=True)     # e.g. "09:00" — due time

    # Status
    is_active = Column(Boolean, default=True)
    last_generated = Column(DateTime(timezone=True), nullable=True)
    next_due = Column(DateTime(timezone=True), nullable=True)

    # Creator
    creator_id = Column(BigInteger, nullable=False, default=0)
    creator_name = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<RecurringTask(id={self.id}, title={self.title[:30]}, recurrence={self.recurrence})>"
