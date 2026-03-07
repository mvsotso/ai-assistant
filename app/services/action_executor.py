"""
Action Executor — Executes actions extracted from AI chat responses.
Handles: create_event, create_task, set_reminder
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


async def execute_actions(actions: list[dict], db) -> list[dict]:
    """
    Execute a list of AI-generated actions.
    Returns list of results for each action.
    """
    results = []
    for action in actions:
        try:
            action_type = action.get("action", "")
            if action_type == "create_event":
                result = await _create_event(action, db)
                results.append(result)
            elif action_type == "create_task":
                result = await _create_task(action, db)
                results.append(result)
            elif action_type == "set_reminder":
                result = await _set_reminder(action, db)
                results.append(result)
            else:
                logger.warning(f"Unknown action type: {action_type}")
                results.append({"success": False, "action": action_type, "error": "Unknown action"})
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            results.append({"success": False, "action": action.get("action", "?"), "error": str(e)})
    return results


async def _create_event(action: dict, db) -> dict:
    """Create a Google Calendar event from AI action."""
    from app.services.calendar_svc import calendar_service, token_store
    from app.core.config import get_settings

    settings = get_settings()
    telegram_id = settings.admin_telegram_id
    creds = await token_store.load_token(db, telegram_id)

    if not creds:
        return {"success": False, "action": "create_event", "error": "Google Calendar not connected"}

    title = action.get("title", "Untitled Event")

    # Parse start time
    start_str = action.get("start", action.get("start_time", ""))
    if start_str:
        try:
            start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            # Try to parse common formats
            start_time = datetime.now(timezone.utc) + timedelta(hours=1)
    else:
        start_time = datetime.now(timezone.utc) + timedelta(hours=1)

    # Parse end time or duration
    end_str = action.get("end", action.get("end_time", ""))
    end_time = None
    if end_str:
        try:
            end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            end_time = None

    duration = action.get("duration_minutes", action.get("duration", 60))
    if isinstance(duration, str):
        try:
            duration = int(duration)
        except ValueError:
            duration = 60

    description = action.get("description", "")
    location = action.get("location", "")
    tz = action.get("timezone", "Asia/Phnom_Penh")

    event = await calendar_service.create_event(
        creds,
        title=title,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=duration,
        description=description,
        location=location,
        tz=tz,
    )

    logger.info(f"Created calendar event: {title}")
    return {
        "success": True,
        "action": "create_event",
        "event": event,
        "message": f"📅 Event '{title}' created successfully!",
    }


async def _create_task(action: dict, db) -> dict:
    """Create a task from AI action."""
    from app.models.task import Task, TaskStatus, TaskPriority
    from app.core.config import get_settings

    settings = get_settings()

    title = action.get("title", "Untitled Task")

    # Map priority
    priority_str = action.get("priority", "medium").lower()
    try:
        priority = TaskPriority(priority_str)
    except (ValueError, KeyError):
        priority = TaskPriority.MEDIUM

    # Parse due date
    due_date = None
    due_str = action.get("due", action.get("due_date", ""))
    if due_str:
        try:
            due_date = datetime.fromisoformat(due_str.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            due_date = None

    task = Task(
        title=title,
        description=action.get("description", ""),
        status=TaskStatus.TODO,
        priority=priority,
        category=action.get("category", action.get("label", None)),
        assignee_name=action.get("assignee", None),
        creator_id=int(settings.admin_telegram_id) if settings.admin_telegram_id else 0,
        creator_name="AI Assistant",
        due_date=due_date,
    )
    db.add(task)
    await db.flush()

    logger.info(f"Created task: {title}")
    return {
        "success": True,
        "action": "create_task",
        "task_id": task.id,
        "message": f"📋 Task '{title}' created successfully!",
    }


async def _set_reminder(action: dict, db) -> dict:
    """Set a reminder from AI action."""
    from app.models.reminder import Reminder
    from app.core.config import get_settings

    settings = get_settings()

    message = action.get("message", action.get("title", "Reminder"))
    minutes = action.get("minutes", 30)
    if isinstance(minutes, str):
        try:
            minutes = int(minutes)
        except ValueError:
            minutes = 30

    remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    reminder = Reminder(
        chat_id=int(settings.admin_telegram_id) if settings.admin_telegram_id else 0,
        user_id=int(settings.admin_telegram_id) if settings.admin_telegram_id else 0,
        message=message,
        remind_at=remind_at,
        is_sent=False,
    )
    db.add(reminder)
    await db.flush()

    logger.info(f"Set reminder: {message} in {minutes}min")
    return {
        "success": True,
        "action": "set_reminder",
        "message": f"⏰ Reminder set: '{message}' in {minutes} minutes",
    }
