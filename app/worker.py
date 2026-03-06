"""
Celery Worker — Background task processing for reminders, briefings, and reports.
"""
import asyncio
import logging
from datetime import datetime, timezone
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
    # Check for pending reminders every minute
    "check-reminders": {
        "task": "app.worker.check_reminders",
        "schedule": 60.0,  # every 60 seconds
    },
    # Send daily morning briefing at 8:00 AM Phnom Penh time (1:00 AM UTC)
    "morning-briefing": {
        "task": "app.worker.send_morning_briefing",
        "schedule": crontab(hour=1, minute=0),  # 8:00 AM ICT = 1:00 AM UTC
    },
    # Send daily end-of-day summary at 5:30 PM Phnom Penh time (10:30 AM UTC)
    "daily-summary": {
        "task": "app.worker.send_daily_summary",
        "schedule": crontab(hour=10, minute=30),
    },
    # Check for upcoming meetings and send 5-min reminders
    "meeting-reminders": {
        "task": "app.worker.check_meeting_reminders",
        "schedule": 120.0,  # every 2 minutes
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

            # Gather task data
            tasks = await task_service.get_tasks(db, limit=50)
            pending = [
                {"title": t.title, "status": t.status.value, "assignee": t.assignee_name or "Unassigned"}
                for t in tasks if t.status != TaskStatus.DONE
            ]

            # Generate briefing via AI (calendar events would be added in production)
            events = []  # TODO: Pull from Google Calendar when connected
            unread_count = 0  # TODO: Pull unread message count

            briefing = await ai_engine.generate_daily_summary(pending, events, unread_count)

            await telegram_service.send_message(admin_id, f"☀️ *Morning Briefing*\n\n{briefing}")
            logger.info("Morning briefing sent")

    run_async(_briefing())


@celery_app.task(name="app.worker.send_daily_summary")
def send_daily_summary():
    """Send end-of-day task summary to team groups."""
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
    """Check for upcoming meetings and send pre-meeting reminders via Telegram."""
    # This requires Google Calendar credentials — will be active after Phase 2 OAuth setup
    logger.debug("Meeting reminder check (requires calendar connection)")
    pass
