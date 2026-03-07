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

router = APIRouter(prefix="/api/v1")


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
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
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
    return _task_to_dict(task)


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
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
    return _task_to_dict(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    deleted = await task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


# ─── Categories ───
@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """Get all unique categories and subcategories."""
    cat_result = await db.execute(
        select(Task.category).where(Task.category.isnot(None)).distinct()
    )
    categories = [r[0] for r in cat_result.all() if r[0]]

    subcat_result = await db.execute(
        select(Task.category, Task.subcategory)
        .where(Task.subcategory.isnot(None))
        .distinct()
    )
    subcategories = {}
    for cat, subcat in subcat_result.all():
        if cat and subcat:
            if cat not in subcategories:
                subcategories[cat] = []
            subcategories[cat].append(subcat)

    return {"categories": categories, "subcategories": subcategories}


# ─── Board ───
@router.get("/board")
async def task_board(db: AsyncSession = Depends(get_db)):
    board = await task_service.get_board(db)
    result = {}
    for status, tasks in board.items():
        result[status] = [_task_to_dict(t) for t in tasks]
    return {"board": result}


# ─── Dashboard ───
@router.get("/dashboard")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    stats = await task_service.get_team_stats(db)
    overdue = await task_service.get_overdue_tasks(db)
    all_tasks = await task_service.get_all_tasks(db, limit=50)

    msg_result = await db.execute(select(sqlfunc.count(Message.id)).where(Message.is_command == False))
    total_messages = msg_result.scalar() or 0

    todo = sum(s.get("todo", 0) for s in stats.values())
    in_progress = sum(s.get("in_progress", 0) for s in stats.values())
    review = sum(s.get("review", 0) for s in stats.values())
    done = sum(s.get("done", 0) for s in stats.values())

    return {
        "stats": {
            "total_tasks": todo + in_progress + review + done,
            "todo": todo, "in_progress": in_progress, "review": review, "done": done,
            "overdue": len(overdue), "total_messages": total_messages,
        },
        "team_stats": stats,
        "overdue_tasks": [_task_to_dict(t) for t in overdue],
        "recent_tasks": [_task_to_dict(t) for t in all_tasks[:10]],
    }


# ─── Team ───
@router.get("/team")
async def get_team(db: AsyncSession = Depends(get_db)):
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
async def team_stats(db: AsyncSession = Depends(get_db)):
    stats = await task_service.get_team_stats(db)
    return {"stats": stats}


# ─── Messages ───
@router.get("/messages")
async def get_messages(
    chat_id: Optional[int] = None, limit: int = 50, db: AsyncSession = Depends(get_db)
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
async def get_message_groups(db: AsyncSession = Depends(get_db)):
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
async def summarize_messages(chat_id: int, db: AsyncSession = Depends(get_db)):
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
async def get_reminders(db: AsyncSession = Depends(get_db)):
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
async def create_reminder(body: ReminderCreate, db: AsyncSession = Depends(get_db)):
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
async def delete_reminder(reminder_id: int, db: AsyncSession = Depends(get_db)):
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


@router.post("/ai/chat")
async def ai_chat(body: ChatRequest):
    response = await ai_engine.chat(body.message, context=body.context or "")
    return {"response": response}


# ─── AI Chat with File Upload ───
from fastapi import UploadFile, File, Form

@router.post("/ai/chat-with-file")
async def ai_chat_with_file(
    message: str = Form("Analyze this file"),
    file: UploadFile = File(...),
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
