"""
Collaboration Service - watchers, activity feed, notifications, optimistic locking.
"""
import json
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func as sqlfunc

from app.models.collaboration import TaskWatcher, ActivityLog
from app.models.task import Task

logger = logging.getLogger(__name__)


class CollabService:

    async def watch_task(self, db: AsyncSession, task_id: int, user_email: str) -> bool:
        """Add a watcher to a task."""
        # Check if already watching
        existing = await db.execute(
            select(TaskWatcher).where(
                TaskWatcher.task_id == task_id,
                TaskWatcher.user_email == user_email,
            )
        )
        if existing.scalar_one_or_none():
            return False  # Already watching

        watcher = TaskWatcher(task_id=task_id, user_email=user_email)
        db.add(watcher)
        return True

    async def unwatch_task(self, db: AsyncSession, task_id: int, user_email: str) -> bool:
        """Remove a watcher from a task."""
        result = await db.execute(
            select(TaskWatcher).where(
                TaskWatcher.task_id == task_id,
                TaskWatcher.user_email == user_email,
            )
        )
        watcher = result.scalar_one_or_none()
        if not watcher:
            return False
        await db.delete(watcher)
        return True

    async def get_watchers(self, db: AsyncSession, task_id: int) -> list:
        """Get all watchers for a task."""
        result = await db.execute(
            select(TaskWatcher).where(TaskWatcher.task_id == task_id)
        )
        return [{"email": w.user_email, "since": w.created_at.isoformat() if w.created_at else None}
                for w in result.scalars().all()]

    async def is_watching(self, db: AsyncSession, task_id: int, user_email: str) -> bool:
        """Check if user is watching a task."""
        result = await db.execute(
            select(TaskWatcher).where(
                TaskWatcher.task_id == task_id,
                TaskWatcher.user_email == user_email,
            )
        )
        return result.scalar_one_or_none() is not None

    async def log_activity(self, db: AsyncSession, entity_type: str, entity_id: int,
                           action: str, user_email: str = None, details: dict = None):
        """Log an activity event."""
        log = ActivityLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            user_email=user_email,
            details_json=json.dumps(details) if details else None,
        )
        db.add(log)

    async def get_activity_feed(self, db: AsyncSession, limit: int = 50,
                                 entity_type: str = None) -> list:
        """Get recent activity feed."""
        query = select(ActivityLog).order_by(desc(ActivityLog.created_at)).limit(limit)
        if entity_type:
            query = query.where(ActivityLog.entity_type == entity_type)

        result = await db.execute(query)
        logs = result.scalars().all()
        return [{
            "id": l.id,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "action": l.action,
            "user_email": l.user_email,
            "details": json.loads(l.details_json) if l.details_json else {},
            "created_at": l.created_at.isoformat() if l.created_at else None,
        } for l in logs]

    async def notify_watchers(self, db: AsyncSession, task_id: int,
                               action: str, actor_email: str, task_title: str = ""):
        """Notify all watchers of a task (except the actor)."""
        watchers = await db.execute(
            select(TaskWatcher).where(
                TaskWatcher.task_id == task_id,
                TaskWatcher.user_email != actor_email,
            )
        )
        for watcher in watchers.scalars().all():
            try:
                from app.services.notification_svc import create_notification
                await create_notification(
                    db, user_id=0, notif_type="task_updated",
                    title=f"Task updated: {task_title} ({action})",
                    entity_id=task_id, entity_type="task",
                )
            except Exception as e:
                logger.debug(f"Watcher notification skipped: {e}")

    async def check_version(self, db: AsyncSession, task_id: int, expected_version: int) -> bool:
        """Check if task version matches expected (optimistic locking)."""
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            return False
        current_version = getattr(task, 'version', 1) or 1
        return current_version == expected_version


collab_service = CollabService()
