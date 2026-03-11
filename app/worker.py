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
    "send-scheduled-reports": {
        "task": "app.worker.send_scheduled_reports",
        "schedule": crontab(hour=0, minute=0),  # 7:00 AM ICT = 0:00 UTC
    },
    "check-auto-escalation": {
        "task": "app.worker.check_auto_escalation",
        "schedule": 14400.0,  # Every 4 hours
    },
}


def run_async(coro):
    """Helper to run async functions in Celery tasks."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _calc_next_reminder(current_at, rule):
    """Calculate next reminder time based on recurrence rule."""
    rule = (rule or "daily").lower().strip()
    if rule == "daily":
        return current_at + timedelta(days=1)
    elif rule == "weekly":
        return current_at + timedelta(weeks=1)
    elif rule == "monthly":
        return current_at + timedelta(days=30)
    elif rule.startswith("custom:"):
        # custom:3d, custom:2w, custom:12h
        val = rule.split(":")[1] if ":" in rule else "1d"
        num = int(''.join(c for c in val if c.isdigit()) or '1')
        unit = val[-1] if val else 'd'
        if unit == 'h':
            return current_at + timedelta(hours=num)
        elif unit == 'w':
            return current_at + timedelta(weeks=num)
        else:
            return current_at + timedelta(days=num)
    return current_at + timedelta(days=1)


@celery_app.task(name="app.worker.check_reminders")
def check_reminders():
    """Check for pending reminders and send them via Telegram with snooze buttons."""
    from app.core.database import async_session
    from app.models.reminder import Reminder
    from app.models.task import Task
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
                    # Build message text
                    msg = f"\u23f0 *Reminder!*\n\n{r.message}"

                    # Add linked task info if available
                    if r.task_id:
                        t_result = await db.execute(select(Task).where(Task.id == r.task_id))
                        linked_task = t_result.scalar_one_or_none()
                        if linked_task:
                            msg += f"\n\n\U0001f4cb *Task #{linked_task.id}:* {linked_task.title}"

                    # Add snooze count if snoozed before
                    if r.snooze_count and r.snooze_count > 0:
                        msg += f"\n\n\U0001f504 _Snoozed {r.snooze_count} time(s)_"

                    # Inline keyboard with snooze buttons
                    inline_keyboard = [[
                        {"text": "\u23f0 15m", "callback_data": f"snooze_15_{r.id}"},
                        {"text": "\u23f0 1h", "callback_data": f"snooze_60_{r.id}"},
                        {"text": "\U0001f305 Tomorrow", "callback_data": f"snooze_1440_{r.id}"},
                    ]]

                    result_msg = await telegram_service.send_message_with_inline_keyboard(
                        r.chat_id, msg, inline_keyboard
                    )

                    r.is_sent = True
                    # Store telegram message_id for later keyboard editing
                    if result_msg.get("ok") and result_msg.get("result"):
                        r.telegram_message_id = result_msg["result"].get("message_id")

                    # Handle recurring reminders — auto-reschedule
                    if r.is_recurring and r.recurrence_rule:
                        next_at = _calc_next_reminder(r.remind_at, r.recurrence_rule)
                        if next_at:
                            r.is_sent = False
                            r.remind_at = next_at
                            r.snooze_count = 0
                            r.telegram_message_id = None
                            logger.info(f"Recurring reminder {r.id} rescheduled to {next_at}")

                    # Send web push notification too
                    try:
                        from app.services.notification_svc import send_push_notification
                        admin_email = settings.dashboard_allowed_emails.split(",")[0].strip()
                        await send_push_notification(db, admin_email, "Reminder", r.message)
                    except Exception as push_err:
                        logger.debug(f"Push notification skipped: {push_err}")

                    # Send email notification too
                    try:
                        from app.services.email_svc import send_reminder_email
                        admin_email = settings.dashboard_allowed_emails.split(",")[0].strip()
                        await send_reminder_email(db, admin_email, r.message)
                    except Exception as email_err:
                        logger.debug(f"Email notification skipped: {email_err}")

                    logger.info(f"Sent reminder {r.id} to chat {r.chat_id} with snooze buttons")
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


@celery_app.task(name="app.worker.send_scheduled_reports")
def send_scheduled_reports():
    """Send scheduled reports via email."""
    from app.core.database import async_session
    from app.models.saved_report import SavedReport
    from app.services.report_svc import report_service
    from sqlalchemy import select
    import json

    async def _send():
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            day_of_week = now.weekday()  # 0=Monday
            day_of_month = now.day

            result = await db.execute(
                select(SavedReport).where(
                    SavedReport.is_active == True,
                    SavedReport.schedule != "none",
                )
            )
            reports = result.scalars().all()
            sent = 0

            for report in reports:
                try:
                    should_send = False
                    if report.schedule == "daily":
                        should_send = True
                    elif report.schedule == "weekly" and day_of_week == 0:  # Monday
                        should_send = True
                    elif report.schedule == "monthly" and day_of_month == 1:
                        should_send = True

                    if not should_send:
                        continue

                    # Generate report
                    filters = json.loads(report.filters_json) if report.filters_json else {}
                    data = await report_service.generate_report(db, report.report_type, filters)
                    html_content = report_service.export_html(data)

                    # Get recipients
                    recipients = json.loads(report.recipients_json) if report.recipients_json else []
                    if not recipients and report.creator_email:
                        recipients = [report.creator_email]

                    # Send email to each recipient
                    for email in recipients:
                        try:
                            from app.services.email_svc import send_generic_email
                            await send_generic_email(
                                db, email,
                                f"Scheduled Report: {report.name}",
                                html_content,
                            )
                        except Exception as email_err:
                            logger.debug(f"Report email to {email} skipped: {email_err}")

                    report.last_run_at = now
                    sent += 1
                    logger.info(f"Sent scheduled report: {report.name}")

                except Exception as e:
                    logger.error(f"Failed to send report {report.id}: {e}")

            await db.commit()
            logger.info(f"Scheduled reports: {sent} sent")

    run_async(_send())


@celery_app.task(name="app.worker.check_auto_escalation")
def check_auto_escalation():
    """Check for overdue tasks and trigger escalation workflow rules."""
    from app.core.database import async_session
    from app.models.task import Task, TaskStatus
    from app.services.workflow_svc import workflow_service
    from sqlalchemy import select

    async def _check():
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            threshold = now - timedelta(hours=24)

            # Find tasks overdue > 24h that aren't done
            result = await db.execute(
                select(Task).where(
                    Task.due_date < threshold,
                    Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]),
                )
            )
            overdue_tasks = result.scalars().all()

            for task in overdue_tasks:
                try:
                    await workflow_service.evaluate_rules(db, "task_overdue", task)
                except Exception as e:
                    logger.error(f"Escalation check failed for task {task.id}: {e}")

            await db.commit()
            logger.info(f"Auto-escalation check: {len(overdue_tasks)} overdue tasks evaluated")

    run_async(_check())
