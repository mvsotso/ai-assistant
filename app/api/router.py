"""
API Router — Full dashboard API with all endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc, desc, distinct
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.bot.handlers import bot_handlers
from app.services.task_svc import task_service
from app.services.ai_engine import ai_engine
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.message import Message
from app.models.reminder import Reminder
from app.models.user import User
from app.api.auth import require_auth

router = APIRouter(prefix="/api/v1")

# Import rate limiter (shared with main.py via Redis)
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings as _get_settings
limiter = Limiter(key_func=get_remote_address, storage_uri=_get_settings().redis_url)


# ─── Health ───
@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "AI Personal Assistant", "timestamp": datetime.utcnow().isoformat()}



# ─── Telegram Webhook ───
@router.post("/webhook/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    try:
        update = await request.json()
        await bot_handlers.handle_update(update, db)
        return {"ok": True}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Webhook error: {e}")
        return {"ok": True}


# ─── Task CRUD ───
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    status: str = "todo"
    assignee_name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    label: Optional[str] = None
    due_date: Optional[str] = None  # ISO date string


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    label: Optional[str] = None
    due_date: Optional[str] = None


def _task_to_dict(t: Task) -> dict:
    return {
        "id": t.id, "title": t.title, "description": t.description,
        "status": t.status.value, "priority": t.priority.value,
        "assignee": t.assignee_name, "creator": t.creator_name,
        "category": getattr(t, "category", None), "subcategory": getattr(t, "subcategory", None),
        "label": t.label,
        "group_id": getattr(t, "group_id", None), "subgroup_id": getattr(t, "subgroup_id", None),
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    category: Optional[str] = None,
    assignee: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    query = select(Task).order_by(Task.created_at.desc()).limit(limit)
    if status:
        query = query.where(Task.status == TaskStatus(status))
    if category:
        query = query.where(Task.category == category)
    if assignee:
        query = query.where(Task.assignee_name == assignee)
    result = await db.execute(query)
    tasks = list(result.scalars().all())
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@router.post("/tasks")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    due = None
    if body.due_date:
        try:
            due = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    try:
        priority = TaskPriority(body.priority)
    except ValueError:
        priority = TaskPriority.MEDIUM
    task = await task_service.create_task(
        db, title=body.title, description=body.description,
        creator_id=0, creator_name="Dashboard",
        priority=priority, assignee_name=body.assignee_name,
        due_date=due, label=body.label,
    )
    # Set category/subcategory
    if body.category:
        task.category = body.category
    if body.subcategory:
        task.subcategory = body.subcategory
    if body.status and body.status != "todo":
        try:
            task.status = TaskStatus(body.status)
        except ValueError:
            pass
    await db.flush()
    await db.refresh(task)
    # Notification: task created
    from app.services.notification_svc import create_notification
    await create_notification(db, user_id=0, notif_type="task_created",
        title=f"New task: {task.title}", entity_id=task.id, entity_type="task")
    return _task_to_dict(task)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    task = await task_service.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.title is not None: task.title = body.title
    if body.description is not None: task.description = body.description
    if body.status is not None:
        try:
            task.status = TaskStatus(body.status)
            if task.status == TaskStatus.DONE:
                task.completed_at = datetime.now(timezone.utc)
        except ValueError:
            pass
    if body.priority is not None:
        try:
            task.priority = TaskPriority(body.priority)
        except ValueError:
            pass
    if body.assignee_name is not None: task.assignee_name = body.assignee_name
    if body.category is not None: task.category = body.category
    if body.subcategory is not None: task.subcategory = body.subcategory
    if body.label is not None: task.label = body.label
    if body.due_date is not None:
        try:
            task.due_date = datetime.fromisoformat(body.due_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    await db.flush()
    # Notification: status changed
    if body.status is not None:
        from app.services.notification_svc import create_notification
        await create_notification(db, user_id=0, notif_type="task_status",
            title=f"Task '{task.title}' → {body.status}", entity_id=task.id, entity_type="task")
    return _task_to_dict(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    deleted = await task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


# ─── Categories ───
# Categories endpoint moved to category_api.py


# ─── Board ───
@router.get("/board")
async def task_board(db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    board = await task_service.get_board(db)
    result = {}
    for status, tasks in board.items():
        result[status] = [_task_to_dict(t) for t in tasks]
    return {"board": result}


# ─── Dashboard ───
@router.get("/dashboard")
async def dashboard_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    # Parse date range filters
    dt_start = None
    dt_end = None
    if start_date:
        try:
            dt_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except ValueError:
            pass
    if end_date:
        try:
            dt_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if dt_end.hour == 0 and dt_end.minute == 0:
                dt_end = dt_end + timedelta(days=1)  # Include full end day
        except ValueError:
            pass

    # Build task query with date range
    task_query = select(Task).order_by(Task.created_at.desc())
    if dt_start:
        task_query = task_query.where(Task.created_at >= dt_start)
    if dt_end:
        task_query = task_query.where(Task.created_at <= dt_end)
    result = await db.execute(task_query.limit(200))
    filtered_tasks = list(result.scalars().all())

    # Compute stats from filtered tasks
    todo = sum(1 for t in filtered_tasks if t.status == TaskStatus.TODO)
    in_progress = sum(1 for t in filtered_tasks if t.status == TaskStatus.IN_PROGRESS)
    review = sum(1 for t in filtered_tasks if t.status == TaskStatus.REVIEW)
    done = sum(1 for t in filtered_tasks if t.status == TaskStatus.DONE)

    overdue = await task_service.get_overdue_tasks(db)

    # Team stats from filtered tasks
    team_stats = {}
    for t in filtered_tasks:
        name = t.assignee_name or "Unassigned"
        if name not in team_stats:
            team_stats[name] = {"todo": 0, "in_progress": 0, "review": 0, "done": 0}
        team_stats[name][t.status.value] = team_stats[name].get(t.status.value, 0) + 1

    msg_result = await db.execute(select(sqlfunc.count(Message.id)).where(Message.is_command == False))
    total_messages = msg_result.scalar() or 0

    # Completion trend (daily done counts for chart)
    trend_days = 7
    trend = []
    now = datetime.now(timezone.utc)
    for i in range(trend_days - 1, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        cnt_r = await db.execute(
            select(sqlfunc.count(Task.id)).where(
                Task.completed_at >= day_start,
                Task.completed_at < day_end,
            )
        )
        trend.append({"date": day.isoformat(), "count": cnt_r.scalar() or 0})

    return {
        "stats": {
            "total_tasks": todo + in_progress + review + done,
            "todo": todo, "in_progress": in_progress, "review": review, "done": done,
            "overdue": len(overdue), "total_messages": total_messages,
        },
        "team_stats": team_stats,
        "overdue_tasks": [_task_to_dict(t) for t in overdue],
        "recent_tasks": [_task_to_dict(t) for t in filtered_tasks[:10]],
        "completion_trend": trend,
    }


# ─── Team ───
@router.get("/team")
async def get_team(db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get all registered team members."""
    result = await db.execute(select(User).order_by(User.created_at.asc()))
    users = list(result.scalars().all())
    return {
        "members": [
            {
                "telegram_id": u.telegram_id, "username": u.telegram_username,
                "first_name": u.first_name, "last_name": u.last_name,
                "is_admin": u.is_admin, "is_active": u.is_active,
            }
            for u in users
        ]
    }


@router.get("/team/stats")
async def team_stats(db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    stats = await task_service.get_team_stats(db)
    return {"stats": stats}


# ─── Messages ───
@router.get("/messages")
async def get_messages(
    chat_id: Optional[int] = None, limit: int = 50, db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get recent messages, optionally filtered by chat."""
    query = select(Message).where(Message.is_command == False).order_by(desc(Message.created_at)).limit(limit)
    if chat_id:
        query = query.where(Message.chat_id == chat_id)
    result = await db.execute(query)
    messages = list(result.scalars().all())
    return {
        "messages": [
            {
                "id": m.id, "chat_id": m.chat_id, "chat_title": m.chat_title,
                "sender": m.sender_name, "text": m.text,
                "has_task_keyword": m.has_task_keyword,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    }


@router.get("/messages/groups")
async def get_message_groups(db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get list of chat groups with message counts."""
    result = await db.execute(
        select(Message.chat_id, Message.chat_title, sqlfunc.count(Message.id))
        .where(Message.chat_title.isnot(None))
        .group_by(Message.chat_id, Message.chat_title)
        .order_by(sqlfunc.count(Message.id).desc())
    )
    groups = [{"chat_id": r[0], "title": r[1], "count": r[2]} for r in result.all()]
    return {"groups": groups}


@router.post("/messages/summarize")
async def summarize_messages(chat_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Summarize messages from a specific chat group."""
    result = await db.execute(
        select(Message).where(Message.chat_id == chat_id, Message.is_command == False)
        .order_by(desc(Message.created_at)).limit(50)
    )
    messages = list(result.scalars().all())
    if not messages:
        return {"summary": "No messages to summarize."}
    msg_dicts = [{"sender": m.sender_name, "text": m.text} for m in reversed(messages) if m.text]
    summary = await ai_engine.summarize_messages(msg_dicts)
    return {"summary": summary}


# ─── Reminders ───
class ReminderCreate(BaseModel):
    minutes: int
    message: str


@router.get("/reminders")
async def get_reminders(db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get all pending reminders."""
    result = await db.execute(
        select(Reminder).where(Reminder.is_sent == False).order_by(Reminder.remind_at.asc())
    )
    reminders = list(result.scalars().all())
    return {
        "reminders": [
            {
                "id": r.id, "message": r.message, "is_sent": r.is_sent,
                "remind_at": r.remind_at.isoformat() if r.remind_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in reminders
        ]
    }


@router.post("/reminders")
async def create_reminder(body: ReminderCreate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Create a reminder from the web dashboard."""
    from app.core.config import get_settings
    settings = get_settings()
    admin_id = int(settings.admin_telegram_id) if settings.admin_telegram_id else 0
    remind_at = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    reminder = Reminder(
        user_id=admin_id, chat_id=admin_id,
        message=body.message, remind_at=remind_at,
    )
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)
    return {"id": reminder.id, "message": reminder.message, "remind_at": remind_at.isoformat()}


@router.delete("/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
    return {"deleted": True}


# ─── AI Chat ───
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    history: Optional[list] = None


@router.post("/ai/chat")
@limiter.limit("10/minute")
async def ai_chat(request: Request, body: ChatRequest, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    response, actions = await ai_engine.chat_with_actions(body.message, context=body.context or "", history=body.history)
    action_results = []
    if actions:
        from app.services.action_executor import execute_actions
        action_results = await execute_actions(actions, db)
        await db.commit()
        for r in action_results:
            if r.get("success"):
                response += "\n\n" + r.get("message", "Action completed.")
            else:
                response += "\n\n\u274c " + r.get("error", "Action failed.")
    return {"response": response, "actions": action_results}


# ─── AI Chat with File Upload ───
from fastapi import UploadFile, File, Form

@router.post("/ai/chat-with-file")
@limiter.limit("10/minute")
async def ai_chat_with_file(
    request: Request,
    message: str = Form("Analyze this file"),
    file: UploadFile = File(...),
    _auth: dict = Depends(require_auth),
):
    """Chat with AI and attach a file for analysis."""
    from app.services.file_processor import extract_text_from_file

    # Read file
    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(status_code=413, detail="File too large. Maximum 10MB.")

    # Extract content
    file_data = await extract_text_from_file(file_bytes, file.filename)

    # Call AI with file
    response = await ai_engine.chat_with_file(message, file_data)
    return {"response": response, "file_summary": file_data["summary"]}

# ─── MoM Processor ───
MOM_EXTRACT_PROMPT = """You are analyzing Meeting Minutes (MoM) documents. Extract ALL action items, decisions, and follow-ups.

For each action item provide:
- title: Brief action-oriented title (max 100 chars)
- assignee: Person name if mentioned, otherwise null
- deadline: ISO date (YYYY-MM-DD) if mentioned, otherwise null
- priority: "low", "medium", "high", or "urgent"
- category: One of: Administration, Data Management, IT & Systems, Tax Operations, Project Management, Communication, Research. Or null.
- type: "task" for action items/deliverables, "reminder" for follow-ups needing a nudge, "event" for scheduled meetings/reviews with a date/time
- event_date: ISO datetime (YYYY-MM-DDTHH:MM:SS+07:00) if type is "event", otherwise null
- event_duration_minutes: integer if type is "event", default 60
- notes: Additional context (max 200 chars)

Respond ONLY with valid JSON, no markdown:
{"meeting_title": "...", "meeting_date": "YYYY-MM-DD or null", "items": [{"title": "...", "assignee": null, "deadline": null, "priority": "medium", "category": null, "type": "task", "event_date": null, "event_duration_minutes": 60, "notes": ""}]}"""


@router.post("/mom/process")
@limiter.limit("5/minute")
async def mom_process(
    request: Request,
    file: UploadFile = File(...),
    _auth: dict = Depends(require_auth),
):
    """Process a MoM document and extract action items via AI."""
    from app.services.file_processor import extract_text_from_file
    import json as json_mod

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum 10MB.")

    file_data = await extract_text_from_file(file_bytes, file.filename)
    if not file_data.get("content"):
        raise HTTPException(status_code=422, detail="Could not extract text from file.")

    prompt = MOM_EXTRACT_PROMPT + "\n\nDocument content:\n" + file_data["content"][:40000]
    result = await ai_engine._call_claude(
        "You extract structured action items from meeting minutes. Respond ONLY with valid JSON.",
        prompt,
        max_tokens=4000,
    )

    try:
        clean = result.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            clean = clean.rsplit("```", 1)[0]
        parsed = json_mod.loads(clean)
    except (json_mod.JSONDecodeError, Exception):
        raise HTTPException(status_code=500, detail="AI failed to extract structured data. Please try again.")

    items = parsed.get("items", [])
    return {
        "meeting_title": parsed.get("meeting_title", file.filename),
        "meeting_date": parsed.get("meeting_date"),
        "items": items,
        "total": len(items),
        "file_summary": file_data.get("summary", ""),
    }


class MomExecuteRequest(BaseModel):
    meeting_title: Optional[str] = None
    items: list


@router.post("/mom/execute")
async def mom_execute(
    body: MomExecuteRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Execute reviewed MoM action items - create tasks, reminders, events."""
    from app.services.action_executor import execute_actions
    from datetime import datetime, timezone, timedelta

    actions = []
    for item in body.items:
        item_type = item.get("type", "task")
        desc = f"[MoM: {body.meeting_title or 'Meeting'}] {item.get('notes', '')}".strip()

        if item_type == "task":
            actions.append({
                "action": "create_task",
                "title": item["title"],
                "assignee": item.get("assignee"),
                "priority": item.get("priority", "medium"),
                "category": item.get("category"),
                "due": item.get("deadline"),
                "description": desc,
            })
        elif item_type == "reminder":
            minutes = 1440  # default 24 hours
            if item.get("deadline"):
                try:
                    deadline = datetime.fromisoformat(item["deadline"].replace("Z", "+00:00"))
                    if deadline.tzinfo is None:
                        deadline = deadline.replace(tzinfo=timezone.utc)
                    diff = (deadline - datetime.now(timezone.utc)).total_seconds() / 60
                    minutes = max(int(diff), 5)
                except (ValueError, TypeError):
                    pass
            actions.append({
                "action": "set_reminder",
                "message": f"[MoM] {item['title']}",
                "minutes": minutes,
            })
        elif item_type == "event":
            actions.append({
                "action": "create_event",
                "title": item["title"],
                "start": item.get("event_date"),
                "duration_minutes": item.get("event_duration_minutes", 60),
                "description": desc,
                "timezone": "Asia/Phnom_Penh",
            })

    results = await execute_actions(actions, db)
    await db.commit()

    created = sum(1 for r in results if r.get("success"))
    failed = sum(1 for r in results if not r.get("success"))

    return {
        "total": len(results),
        "created": created,
        "failed": failed,
        "results": results,
    }
