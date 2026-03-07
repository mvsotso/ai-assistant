"""
Celery Worker — Background task processing for reminders, briefings, reports,
and recurring task generation.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# Initialize Celery
celery_app = Celery(
    "ai_assistant",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Phnom_Penh",
    enable_utc=True,
)

# ─── Scheduled Tasks ───
celery_app.conf.beat_schedule = {
    "check-reminders": {
        "task": "app.worker.check_reminders",
        "schedule": 60.0,
    },
    "morning-briefing": {
        "task": "app.worker.send_morning_briefing",
        "schedule": crontab(hour=1, minute=0),  # 8:00 AM ICT
    },
    "daily-summary": {
        "task": "app.worker.send_daily_summary",
        "schedule": crontab(hour=10, minute=30),  # 5:30 PM ICT
    },
    "meeting-reminders": {
        "task": "app.worker.check_meeting_reminders",
        "schedule": 120.0,
    },
    # Generate recurring tasks every day at 1:00 AM ICT (6:00 PM UTC prev day)
    "generate-recurring-tasks": {
        "task": "app.worker.generate_recurring_tasks",
        "schedule": crontab(hour=18, minute=0),  # 1:00 AM ICT = 6:00 PM UTC
    },
}


def run_async(coro):
    """Helper to run async functions in Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="app.worker.check_reminders")
def check_reminders():
    """Check for pending reminders and send them via Telegram."""
    from app.core.database import async_session
    from app.models.reminder import Reminder
    from app.services.telegram import telegram_service
    from sqlalchemy import select

    async def _check():
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            result = await db.execute(
                select(Reminder).where(
                    Reminder.is_sent == False,
                    Reminder.remind_at <= now,
                )
            )
            reminders = result.scalars().all()

            for r in reminders:
                try:
                    await telegram_service.send_message(
                        r.chat_id,
                        f"⏰ *Reminder!*\n\n{r.message}"
                    )
                    r.is_sent = True
                    logger.info(f"Sent reminder {r.id} to chat {r.chat_id}")
                except Exception as e:
                    logger.error(f"Failed to send reminder {r.id}: {e}")

            await db.commit()

    run_async(_check())


@celery_app.task(name="app.worker.send_morning_briefing")
def send_morning_briefing():
    """Send daily morning briefing to admin user."""
    from app.core.database import async_session
    from app.services.ai_engine import ai_engine
    from app.services.telegram import telegram_service
    from app.services.task_svc import task_service
    from app.models.task import TaskStatus

    async def _briefing():
        async with async_session() as db:
            admin_id = int(settings.admin_telegram_id) if settings.admin_telegram_id else None
            if not admin_id:
                return

            tasks = await task_service.get_tasks(db, limit=50)
            pending = [
                {"title": t.title, "status": t.status.value, "assignee": t.assignee_name or "Unassigned"}
                for t in tasks if t.status != TaskStatus.DONE
            ]

            events = []
            unread_count = 0

            briefing = await ai_engine.generate_daily_summary(pending, events, unread_count)
            await telegram_service.send_message(admin_id, f"☀️ *Morning Briefing*\n\n{briefing}")
            logger.info("Morning briefing sent")

    run_async(_briefing())


@celery_app.task(name="app.worker.send_daily_summary")
def send_daily_summary():
    """Send end-of-day task summary."""
    from app.core.database import async_session
    from app.services.ai_engine import ai_engine
    from app.services.telegram import telegram_service
    from app.services.task_svc import task_service
    from app.models.task import TaskStatus

    async def _summary():
        async with async_session() as db:
            admin_id = int(settings.admin_telegram_id) if settings.admin_telegram_id else None
            if not admin_id:
                return

            tasks = await task_service.get_tasks(db, limit=100)
            completed = [
                {"title": t.title, "assignee": t.assignee_name or "Unknown"}
                for t in tasks if t.status == TaskStatus.DONE
            ]
            in_progress = [
                {"title": t.title, "assignee": t.assignee_name or "Unknown"}
                for t in tasks if t.status == TaskStatus.IN_PROGRESS
            ]
            stats = await task_service.get_team_stats(db)

            report = await ai_engine.generate_weekly_report(completed, in_progress, stats)
            await telegram_service.send_message(admin_id, f"📊 *Daily Summary*\n\n{report}")
            logger.info("Daily summary sent")

    run_async(_summary())


@celery_app.task(name="app.worker.check_meeting_reminders")
def check_meeting_reminders():
    """Check for upcoming meetings and send pre-meeting reminders."""
    logger.debug("Meeting reminder check (requires calendar connection)")
    pass


@celery_app.task(name="app.worker.generate_recurring_tasks")
def generate_recurring_tasks():
    """
    Generate tasks from active recurring task templates.
    Runs daily — checks each template and creates a task if due today or overdue.
    """
    from app.core.database import async_session
    from app.models.recurring_task import RecurringTask
    from app.models.task import Task, TaskStatus, TaskPriority
    from sqlalchemy import select

    async def _generate():
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            today = now.date()

            # Get all active recurring tasks
            result = await db.execute(
                select(RecurringTask).where(RecurringTask.is_active == True)
            )
            templates = result.scalars().all()
            generated = 0

            for tmpl in templates:
                try:
                    should_generate = False

                    if tmpl.next_due and tmpl.next_due.date() <= today:
                        should_generate = True
                    elif not tmpl.last_generated:
                        should_generate = True

                    if not should_generate:
                        continue

                    # Check if we already generated today (avoid duplicates)
                    if tmpl.last_generated and tmpl.last_generated.date() == today:
                        continue

                    # Parse due time
                    hour, minute = 9, 0
                    if tmpl.time_of_day:
                        try:
                            parts = tmpl.time_of_day.split(":")
                            hour, minute = int(parts[0]), int(parts[1])
                        except (ValueError, IndexError):
                            pass

                    due_dt = datetime(today.year, today.month, today.day, hour, minute, tzinfo=timezone.utc)

                    # Map priority string to enum
                    try:
                        priority = TaskPriority(tmpl.priority)
                    except (ValueError, KeyError):
                        priority = TaskPriority.MEDIUM

                    # Create the task
                    task = Task(
                        title=tmpl.title,
                        description=tmpl.description or f"[Auto-generated from recurring template #{tmpl.id}]",
                        status=TaskStatus.TODO,
                        priority=priority,
                        category=tmpl.category,
                        subcategory=tmpl.subcategory,
                        assignee_name=tmpl.assignee_name,
                        creator_id=tmpl.creator_id or 0,
                        creator_name=tmpl.creator_name or "System",
                        due_date=due_dt,
                    )
                    db.add(task)

                    # Update template
                    tmpl.last_generated = now
                    tmpl.next_due = _calc_next(tmpl)

                    generated += 1
                    logger.info(f"Generated recurring task: '{tmpl.title}' (template #{tmpl.id})")

                except Exception as e:
                    logger.error(f"Failed to generate recurring task #{tmpl.id}: {e}")

            await db.commit()
            logger.info(f"Recurring task generation complete: {generated} task(s) created")

    def _calc_next(tmpl):
        """Calculate next due date after generation."""
        from app.api.recurring_api import _calc_next_due
        return _calc_next_due(
            tmpl.recurrence.value, tmpl.day_of_week, tmpl.day_of_month,
            tmpl.month_of_year, tmpl.quarter_months, tmpl.semi_months,
        )

    run_async(_generate())
