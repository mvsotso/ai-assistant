"""
API Router — aggregates all API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.bot.handlers import bot_handlers
from app.services.task_svc import task_service
from app.services.ai_engine import ai_engine
from app.models.task import TaskStatus, TaskPriority

router = APIRouter(prefix="/api/v1")


# ─── Health ───
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Personal Assistant",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── Telegram Webhook ───
@router.post("/webhook/telegram")
async def telegram_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receive and process Telegram updates."""
    try:
        update = await request.json()
        await bot_handlers.handle_update(update, db)
        return {"ok": True}
    except Exception as e:
        # Log but don't fail — Telegram retries on 5xx
        import logging
        logging.getLogger(__name__).error(f"Webhook error: {e}")
        return {"ok": True}


# ─── Task API ───
class TaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_name: Optional[str] = None
    due_date: Optional[datetime] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[TaskPriority] = None
    assignee_name: Optional[str] = None
    due_date: Optional[datetime] = None


@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
):
    """List tasks with optional status filter."""
    task_status = TaskStatus(status) if status else None
    tasks = await task_service.get_tasks(db, status=task_status, limit=limit)
    return {
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "status": t.status.value,
                "priority": t.priority.value,
                "assignee": t.assignee_name,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    }


@router.post("/tasks")
async def create_task(body: TaskCreate, db: AsyncSession = Depends(get_db)):
    """Create a new task via API."""
    task = await task_service.create_task(
        db,
        title=body.title,
        description=body.description,
        creator_id=0,  # API-created
        creator_name="API",
        priority=body.priority,
        assignee_name=body.assignee_name,
        due_date=body.due_date,
    )
    return {"id": task.id, "title": task.title, "status": task.status.value}


@router.patch("/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db)):
    """Update an existing task."""
    task = await task_service.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if body.title is not None:
        task.title = body.title
    if body.description is not None:
        task.description = body.description
    if body.status is not None:
        task.status = body.status
        if body.status == TaskStatus.DONE:
            task.completed_at = datetime.utcnow()
    if body.priority is not None:
        task.priority = body.priority
    if body.assignee_name is not None:
        task.assignee_name = body.assignee_name
    if body.due_date is not None:
        task.due_date = body.due_date

    await db.flush()
    return {"id": task.id, "title": task.title, "status": task.status.value}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a task."""
    deleted = await task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"deleted": True}


# ─── AI Chat API ───
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None


@router.post("/ai/chat")
async def ai_chat(body: ChatRequest):
    """Chat with the AI assistant via API."""
    response = await ai_engine.chat(body.message, context=body.context or "")
    return {"response": response}


# ─── Team Stats ───
@router.get("/stats/team")
async def team_stats(db: AsyncSession = Depends(get_db)):
    """Get team task statistics."""
    stats = await task_service.get_team_stats(db)
    return {"stats": stats}


# ─── Board View ───
@router.get("/board")
async def task_board(db: AsyncSession = Depends(get_db)):
    """Get tasks grouped by status for Kanban board."""
    board = await task_service.get_board(db)
    result = {}
    for status, tasks in board.items():
        result[status] = [
            {
                "id": t.id, "title": t.title, "description": t.description,
                "status": t.status.value, "priority": t.priority.value,
                "assignee": t.assignee_name, "label": t.label,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
    return {"board": result}


# ─── Dashboard Summary ───
@router.get("/dashboard")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    """Get dashboard overview data."""
    from app.models.message import Message
    from sqlalchemy import func as sqlfunc, desc

    stats = await task_service.get_team_stats(db)
    overdue = await task_service.get_overdue_tasks(db)
    all_tasks = await task_service.get_all_tasks(db, limit=50)

    # Recent messages count
    msg_result = await db.execute(
        select(sqlfunc.count(Message.id)).where(Message.is_command == False)
    )
    total_messages = msg_result.scalar() or 0

    # Task counts
    todo = sum(s.get("todo", 0) for s in stats.values())
    in_progress = sum(s.get("in_progress", 0) for s in stats.values())
    review = sum(s.get("review", 0) for s in stats.values())
    done = sum(s.get("done", 0) for s in stats.values())

    return {
        "stats": {
            "total_tasks": todo + in_progress + review + done,
            "todo": todo, "in_progress": in_progress, "review": review, "done": done,
            "overdue": len(overdue),
            "total_messages": total_messages,
        },
        "team_stats": stats,
        "overdue_tasks": [
            {"id": t.id, "title": t.title, "assignee": t.assignee_name, "due_date": t.due_date.isoformat() if t.due_date else None}
            for t in overdue
        ],
        "recent_tasks": [
            {"id": t.id, "title": t.title, "status": t.status.value, "priority": t.priority.value,
             "assignee": t.assignee_name, "label": t.label}
            for t in all_tasks[:10]
        ],
    }
