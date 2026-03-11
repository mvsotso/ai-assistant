"""
Time Tracking Service - timer management and timesheets.
"""
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.models.time_log import TimeLog
from app.models.task import Task

logger = logging.getLogger(__name__)


class TimeService:

    async def start_timer(self, db: AsyncSession, task_id: int, user_email: str) -> TimeLog:
        """Start a timer for a task. Stops any running timer first."""
        # Stop any existing running timer for this user
        running = await db.execute(
            select(TimeLog).where(
                TimeLog.user_email == user_email,
                TimeLog.is_running == True,
            )
        )
        for log in running.scalars().all():
            log.is_running = False
            log.ended_at = datetime.now(timezone.utc)
            if log.started_at:
                log.duration_minutes = round((log.ended_at - log.started_at).total_seconds() / 60, 1)

        # Create new timer
        timer = TimeLog(
            task_id=task_id,
            user_email=user_email,
            started_at=datetime.now(timezone.utc),
            is_running=True,
        )
        db.add(timer)
        await db.flush()
        await db.refresh(timer)
        return timer

    async def stop_timer(self, db: AsyncSession, task_id: int, user_email: str) -> TimeLog:
        """Stop the running timer for a task."""
        result = await db.execute(
            select(TimeLog).where(
                TimeLog.task_id == task_id,
                TimeLog.user_email == user_email,
                TimeLog.is_running == True,
            )
        )
        timer = result.scalar_one_or_none()
        if not timer:
            return None

        timer.is_running = False
        timer.ended_at = datetime.now(timezone.utc)
        if timer.started_at:
            timer.duration_minutes = round((timer.ended_at - timer.started_at).total_seconds() / 60, 1)
        return timer

    async def log_time(self, db: AsyncSession, task_id: int, user_email: str,
                       minutes: float, description: str = None) -> TimeLog:
        """Manually log time for a task."""
        now = datetime.now(timezone.utc)
        log = TimeLog(
            task_id=task_id,
            user_email=user_email,
            description=description,
            started_at=now - timedelta(minutes=minutes),
            ended_at=now,
            duration_minutes=round(minutes, 1),
            is_running=False,
        )
        db.add(log)
        await db.flush()
        await db.refresh(log)
        return log

    async def get_task_time_logs(self, db: AsyncSession, task_id: int) -> list:
        """Get all time logs for a task."""
        result = await db.execute(
            select(TimeLog).where(TimeLog.task_id == task_id)
            .order_by(TimeLog.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_task_time_summary(self, db: AsyncSession, task_id: int) -> dict:
        """Get total time logged for a task."""
        result = await db.execute(
            select(sqlfunc.sum(TimeLog.duration_minutes))
            .where(TimeLog.task_id == task_id)
        )
        total = result.scalar() or 0

        # Get estimated hours from task
        task_result = await db.execute(select(Task).where(Task.id == task_id))
        task = task_result.scalar_one_or_none()
        estimated_hours = getattr(task, 'estimated_hours', None) if task else None

        return {
            "total_minutes": round(total, 1),
            "total_hours": round(total / 60, 1),
            "estimated_hours": estimated_hours,
            "progress_pct": round(total / 60 / estimated_hours * 100) if estimated_hours and estimated_hours > 0 else None,
        }

    async def get_timesheet(self, db: AsyncSession, user_email: str = None,
                            start_date: str = None, end_date: str = None) -> list:
        """Get timesheet grouped by day."""
        query = select(TimeLog).order_by(TimeLog.started_at.desc())
        if user_email:
            query = query.where(TimeLog.user_email == user_email)
        if start_date:
            try:
                dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
                query = query.where(TimeLog.started_at >= dt)
            except ValueError:
                pass
        if end_date:
            try:
                dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                query = query.where(TimeLog.started_at <= dt)
            except ValueError:
                pass

        result = await db.execute(query.limit(200))
        logs = list(result.scalars().all())

        # Group by day
        daily = {}
        for log in logs:
            if log.started_at:
                day = log.started_at.date().isoformat()
            else:
                day = "unknown"
            if day not in daily:
                daily[day] = {"date": day, "entries": [], "total_minutes": 0}
            daily[day]["entries"].append({
                "id": log.id,
                "task_id": log.task_id,
                "description": log.description,
                "duration_minutes": log.duration_minutes,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "ended_at": log.ended_at.isoformat() if log.ended_at else None,
                "is_running": log.is_running,
            })
            daily[day]["total_minutes"] += log.duration_minutes or 0

        return sorted(daily.values(), key=lambda x: x["date"], reverse=True)

    async def get_running_timer(self, db: AsyncSession, user_email: str) -> dict:
        """Get currently running timer for a user."""
        result = await db.execute(
            select(TimeLog).where(
                TimeLog.user_email == user_email,
                TimeLog.is_running == True,
            )
        )
        timer = result.scalar_one_or_none()
        if not timer:
            return None
        elapsed = (datetime.now(timezone.utc) - timer.started_at).total_seconds() / 60 if timer.started_at else 0
        return {
            "id": timer.id,
            "task_id": timer.task_id,
            "started_at": timer.started_at.isoformat() if timer.started_at else None,
            "elapsed_minutes": round(elapsed, 1),
        }

    async def delete_log(self, db: AsyncSession, log_id: int) -> bool:
        """Delete a time log entry."""
        result = await db.execute(select(TimeLog).where(TimeLog.id == log_id))
        log = result.scalar_one_or_none()
        if not log:
            return False
        await db.delete(log)
        return True


time_service = TimeService()
