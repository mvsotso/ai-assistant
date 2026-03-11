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
from app.models.audit_log import AuditLog
from app.models.user import User
from app.api.auth import require_auth, require_permission, verify_session_token
from fastapi.responses import StreamingResponse
import asyncio

router = APIRouter(prefix="/api/v1")

# ─── SSE Real-Time Events ───
async def broadcast_event(event_type: str, data: dict):
    """Broadcast an event to all connected SSE clients via Redis pub/sub."""
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(_get_settings().redis_url)
        import json as _json
        await r.publish("sse_events", _json.dumps({"event": event_type, "data": data}))
        await r.aclose()
    except Exception as e:
        logging.getLogger(__name__).debug(f"SSE broadcast: {e}")

@router.get("/events/stream")
async def event_stream(request: Request, token: str = ""):
    """SSE endpoint for real-time updates. Auth via query param."""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    import redis.asyncio as aioredis

    async def generate():
        r = aioredis.from_url(_get_settings().redis_url)
        pubsub = r.pubsub()
        await pubsub.subscribe("sse_events")
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg and msg["type"] == "message":
                    import json as _j
                    try:
                        evt = _j.loads(msg["data"].decode("utf-8"))
                        yield f"event: {evt.get('event','update')}\ndata: {_j.dumps(evt.get('data',{}))}\n\n"
                    except (ValueError, KeyError):
                        yield f"data: {msg['data'].decode('utf-8')}\n\n"
                else:
                    yield ": keepalive\n\n"
                    await asyncio.sleep(15)
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe("sse_events")
            await pubsub.close()
            await r.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )

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
@limiter.limit("120/minute")
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
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None


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
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None


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


async def log_audit(db, task_id: int, user_email: str, action: str, field: str = None, old_val: str = None, new_val: str = None):
    """Record a task audit log entry."""
    entry = AuditLog(task_id=task_id, user_email=user_email, action=action,
                     field_changed=field, old_value=old_val, new_value=new_val)
    db.add(entry)


@limiter.limit("60/minute")
@router.get("/tasks")
async def list_tasks(request: Request, 
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


@limiter.limit("30/minute")
@router.post("/tasks")
async def create_task(request: Request, body: TaskCreate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
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
    if body.group_id:
        task.group_id = body.group_id
    if body.subgroup_id:
        task.subgroup_id = body.subgroup_id
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
    # Audit log: task created
    await log_audit(db, task.id, _auth.get("email", ""), "created")
    # Email notification: task assigned (best-effort)
    if task.assignee_name:
        try:
            from app.services.email_svc import send_task_assigned_email
            assignee_user = await db.execute(select(User).where(User.first_name == task.assignee_name))
            au = assignee_user.scalar_one_or_none()
            if au and au.email:
                await send_task_assigned_email(db, au.email, task.title, task.assignee_name, task.due_date)
        except Exception:
            pass
    await broadcast_event("task_updated", {"action": "created", "task_id": task.id, "title": task.title})
    return _task_to_dict(task)


@limiter.limit("30/minute")
@router.patch("/tasks/{task_id}")
async def update_task(request: Request, task_id: int, body: TaskUpdate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    task = await task_service.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    email = _auth.get("email", "")
    # Audit: track field changes
    if body.title is not None and body.title != task.title:
        await log_audit(db, task_id, email, "updated", "title", task.title, body.title)
    if body.status is not None and body.status != (task.status.value if task.status else None):
        await log_audit(db, task_id, email, "status_changed", "status", task.status.value if task.status else "", body.status)
    if body.priority is not None and body.priority != (task.priority.value if task.priority else None):
        await log_audit(db, task_id, email, "updated", "priority", task.priority.value if task.priority else "", body.priority)
    if body.assignee_name is not None and body.assignee_name != task.assignee_name:
        await log_audit(db, task_id, email, "updated", "assignee", task.assignee_name or "", body.assignee_name)
    if body.due_date is not None:
        old_due = task.due_date.isoformat() if task.due_date else ""
        await log_audit(db, task_id, email, "updated", "due_date", old_due, body.due_date)
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
    if body.group_id is not None: task.group_id = body.group_id
    if body.subgroup_id is not None: task.subgroup_id = body.subgroup_id
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
    # Email notifications (best-effort)
    try:
        if task.assignee_name:
            assignee_user = await db.execute(select(User).where(User.first_name == task.assignee_name))
            au = assignee_user.scalar_one_or_none()
            if au and au.email:
                if body.status is not None:
                    from app.services.email_svc import send_task_status_email
                    old_st = body.status  # Already logged above with old value
                    await send_task_status_email(db, au.email, task.title, '', body.status)
                if body.assignee_name is not None:
                    from app.services.email_svc import send_task_assigned_email
                    await send_task_assigned_email(db, au.email, task.title, task.assignee_name, task.due_date)
    except Exception:
        pass
    await broadcast_event("task_updated", {"action": "updated", "task_id": task.id, "title": task.title})
    return _task_to_dict(task)


@limiter.limit("30/minute")
@router.delete("/tasks/{task_id}")
async def delete_task(request: Request, task_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_permission("delete"))):
    # Audit log before deletion
    task = await task_service.get_task_by_id(db, task_id)
    if task:
        await log_audit(db, task_id, _auth.get("email", ""), "deleted", None, task.title, None)
    deleted = await task_service.delete_task(db, task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found")
    await broadcast_event("task_updated", {"action": "deleted", "task_id": task_id})
    return {"deleted": True}



@limiter.limit("60/minute")
@router.get("/tasks/{task_id}/audit")
async def get_task_audit(request: Request, task_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get audit trail for a specific task."""
    result = await db.execute(
        select(AuditLog).where(AuditLog.task_id == task_id).order_by(AuditLog.created_at.desc()).limit(50)
    )
    entries = list(result.scalars().all())
    return {"audit": [
        {
            "id": e.id, "task_id": e.task_id, "user_email": e.user_email,
            "action": e.action, "field_changed": e.field_changed,
            "old_value": e.old_value, "new_value": e.new_value,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]}


# ─── Categories ───
# Categories endpoint moved to category_api.py


# ─── Board ───
@limiter.limit("60/minute")
@router.get("/board")
async def task_board(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    board = await task_service.get_board(db)
    result = {}
    for status, tasks in board.items():
        result[status] = [_task_to_dict(t) for t in tasks]
    return {"board": result}


# ─── Dashboard ───
@limiter.limit("60/minute")
@router.get("/dashboard")
async def dashboard_summary(request: Request, 
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

    # ── Burndown data ──
    burndown = []
    if filtered_tasks:
        total_in_period = len(filtered_tasks)
        # Daily burndown: remaining = total - cumulative done up to that day
        for i in range(trend_days - 1, -1, -1):
            day = (now - timedelta(days=i)).date()
            done_by_day = sum(1 for t in filtered_tasks if t.completed_at and t.completed_at.date() <= day)
            remaining = total_in_period - done_by_day
            ideal = max(0, total_in_period - round(total_in_period * (trend_days - i) / trend_days))
            burndown.append({"date": day.isoformat(), "remaining": remaining, "ideal": ideal})

    # ── KPI calculations ──
    completed_tasks = [t for t in filtered_tasks if t.status == TaskStatus.DONE and t.completed_at]
    avg_days = 0
    if completed_tasks:
        total_days = sum((t.completed_at - t.created_at).total_seconds() / 86400 for t in completed_tasks if t.created_at)
        avg_days = round(total_days / len(completed_tasks), 1) if completed_tasks else 0
    on_time = sum(1 for t in completed_tasks if t.due_date and t.completed_at <= t.due_date)
    on_time_pct = round(on_time / len(completed_tasks) * 100) if completed_tasks else 0
    week_ago = now - timedelta(days=7)
    tasks_this_week = sum(1 for t in filtered_tasks if t.created_at and t.created_at >= week_ago)

    # ── Previous period for trend comparison ──
    prev_start = None
    prev_end = None
    prev_stats = {}
    if dt_start and dt_end:
        period_days = (dt_end - dt_start).days
        prev_end = dt_start
        prev_start = prev_end - timedelta(days=period_days)
    elif not dt_start and not dt_end:
        # Default: compare last 7 days to previous 7 days
        prev_end = now - timedelta(days=7)
        prev_start = prev_end - timedelta(days=7)
    if prev_start and prev_end:
        prev_q = select(Task).where(Task.created_at >= prev_start, Task.created_at <= prev_end)
        prev_result = await db.execute(prev_q.limit(200))
        prev_tasks = list(prev_result.scalars().all())
        prev_done = sum(1 for t in prev_tasks if t.status == TaskStatus.DONE)
        prev_total = len(prev_tasks)
        prev_overdue = sum(1 for t in prev_tasks if t.due_date and t.due_date < now and t.status != TaskStatus.DONE)
        prev_completed = [t for t in prev_tasks if t.status == TaskStatus.DONE and t.completed_at]
        prev_avg = 0
        if prev_completed:
            prev_avg = round(sum((t.completed_at - t.created_at).total_seconds() / 86400 for t in prev_completed if t.created_at) / len(prev_completed), 1)
        prev_on_time = sum(1 for t in prev_completed if t.due_date and t.completed_at <= t.due_date)
        prev_on_time_pct = round(prev_on_time / len(prev_completed) * 100) if prev_completed else 0
        prev_stats = {"total": prev_total, "done": prev_done, "overdue": prev_overdue, "avg_days": prev_avg, "on_time_pct": prev_on_time_pct}

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
        "burndown": burndown,
        "kpis": {
            "avg_completion_days": avg_days,
            "on_time_pct": on_time_pct,
            "overdue_count": len(overdue),
            "tasks_this_week": tasks_this_week,
        },
        "previous_period": prev_stats,
    }


# ─── Team ───
@limiter.limit("60/minute")
@router.get("/team")
async def get_team(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
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


@limiter.limit("60/minute")
@router.get("/team/stats")
async def team_stats(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    stats = await task_service.get_team_stats(db)
    return {"stats": stats}


# ─── Messages ───
@limiter.limit("60/minute")
@router.get("/messages")
async def get_messages(request: Request, 
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


@limiter.limit("60/minute")
@router.get("/messages/groups")
async def get_message_groups(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get list of chat groups with message counts."""
    result = await db.execute(
        select(Message.chat_id, Message.chat_title, sqlfunc.count(Message.id))
        .where(Message.chat_title.isnot(None))
        .group_by(Message.chat_id, Message.chat_title)
        .order_by(sqlfunc.count(Message.id).desc())
    )
    groups = [{"chat_id": r[0], "title": r[1], "count": r[2]} for r in result.all()]
    return {"groups": groups}


@limiter.limit("30/minute")
@router.post("/messages/summarize")
async def summarize_messages(request: Request, chat_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
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
    message: str
    minutes: Optional[int] = None      # relative: minutes from now (backward compat)
    remind_at: Optional[str] = None    # absolute: ISO datetime string
    task_id: Optional[int] = None      # optional link to a task
    event_id: Optional[str] = None     # optional link to a calendar event
    is_recurring: Optional[bool] = False    # recurring reminder
    recurrence_rule: Optional[str] = None   # daily, weekly, monthly, custom:3d


class SnoozeRequest(BaseModel):
    minutes: int  # snooze duration in minutes (15, 60, 1440)


@limiter.limit("60/minute")
@router.get("/reminders")
async def get_reminders(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get all pending reminders with linked task info."""
    result = await db.execute(
        select(Reminder).where(Reminder.is_sent == False).order_by(Reminder.remind_at.asc())
    )
    reminders = list(result.scalars().all())
    items = []
    for r in reminders:
        item = {
            "id": r.id, "message": r.message, "is_sent": r.is_sent,
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "task_id": r.task_id, "event_id": r.event_id,
            "snooze_count": r.snooze_count or 0,
            "is_recurring": r.is_recurring or False,
            "recurrence_rule": r.recurrence_rule,
        }
        # Include linked task title if available
        if r.task_id:
            t_result = await db.execute(select(Task).where(Task.id == r.task_id))
            linked_task = t_result.scalar_one_or_none()
            item["task_title"] = linked_task.title if linked_task else None
        items.append(item)
    return {"reminders": items}


@limiter.limit("30/minute")
@router.post("/reminders")
async def create_reminder(request: Request, body: ReminderCreate, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Create a reminder from the web dashboard. Accepts absolute datetime or relative minutes."""
    from app.core.config import get_settings
    settings = get_settings()
    admin_id = int(settings.admin_telegram_id) if settings.admin_telegram_id else 0
    # Determine remind_at: absolute takes priority over relative
    if body.remind_at:
        try:
            remind_at = datetime.fromisoformat(body.remind_at.replace('Z', '+00:00'))
            if remind_at.tzinfo is None:
                remind_at = remind_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid remind_at format. Use ISO datetime.")
    else:
        minutes = body.minutes if body.minutes and body.minutes > 0 else 30
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    reminder = Reminder(
        user_id=admin_id, chat_id=admin_id,
        message=body.message, remind_at=remind_at,
        task_id=body.task_id, event_id=body.event_id,
        is_recurring=body.is_recurring or False,
        recurrence_rule=body.recurrence_rule,
    )
    db.add(reminder)
    await db.flush()
    await db.refresh(reminder)
    return {"id": reminder.id, "message": reminder.message, "remind_at": remind_at.isoformat(), "task_id": reminder.task_id}


@limiter.limit("30/minute")
@router.delete("/reminders/{reminder_id}")
async def delete_reminder(request: Request, reminder_id: int, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    await db.delete(reminder)
    return {"deleted": True}


@limiter.limit("30/minute")
@router.patch("/reminders/{reminder_id}/snooze")
async def snooze_reminder(request: Request, reminder_id: int, body: SnoozeRequest, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Snooze a reminder by X minutes. Resets is_sent so it fires again."""
    result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
    reminder = result.scalar_one_or_none()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    # Store original time on first snooze
    if not reminder.original_remind_at:
        reminder.original_remind_at = reminder.remind_at
    reminder.remind_at = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    reminder.is_sent = False
    reminder.snooze_count = (reminder.snooze_count or 0) + 1
    await db.flush()
    return {"id": reminder.id, "remind_at": reminder.remind_at.isoformat(), "snooze_count": reminder.snooze_count}



@limiter.limit("60/minute")
@router.get("/reminders/history")
async def get_reminder_history(request: Request, limit: int = 50, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get sent/fired reminders history."""
    result = await db.execute(
        select(Reminder).where(Reminder.is_sent == True).order_by(Reminder.remind_at.desc()).limit(limit)
    )
    reminders = list(result.scalars().all())
    items = []
    for r in reminders:
        item = {
            "id": r.id, "message": r.message, "is_sent": r.is_sent,
            "remind_at": r.remind_at.isoformat() if r.remind_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "task_id": r.task_id, "event_id": r.event_id,
            "snooze_count": r.snooze_count or 0,
            "is_recurring": r.is_recurring,
        }
        if r.task_id:
            t_result = await db.execute(select(Task).where(Task.id == r.task_id))
            linked_task = t_result.scalar_one_or_none()
            item["task_title"] = linked_task.title if linked_task else None
        items.append(item)
    return {"reminders": items}



# ─── AI Suggestions ───
@limiter.limit("60/minute")
@router.get("/ai/suggestions")
async def get_ai_suggestions(request: Request, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """Get AI-suggested tasks based on current workload."""
    result = await db.execute(select(Task).order_by(Task.created_at.desc()).limit(50))
    tasks = list(result.scalars().all())
    existing = [{"title": t.title, "status": t.status.value, "assignee": t.assignee_name or "Unassigned", "priority": t.priority.value} for t in tasks]
    completed = [{"title": t.title} for t in tasks if t.status == TaskStatus.DONE][:10]
    suggestions = await ai_engine.suggest_tasks(existing, recent_completed=completed)
    return {"suggestions": suggestions}


@limiter.limit("30/minute")
@router.post("/ai/suggest-time")
async def suggest_reminder_time(request: Request, body: dict, _auth: dict = Depends(require_auth)):
    """AI suggests optimal reminder time for a task."""
    title = body.get("title", "")
    due_date = body.get("due_date", "")
    result = await ai_engine.suggest_reminder_time(title, due_date)
    return result


# ─── AI Prioritize ───
class PrioritizeRequest(BaseModel):
    include_workload: bool = True

@limiter.limit("10/minute")
@router.post("/ai/prioritize")
async def ai_prioritize(request: Request, body: PrioritizeRequest, db: AsyncSession = Depends(get_db), _auth: dict = Depends(require_auth)):
    """AI-powered task prioritization and workload balancing."""
    result = await db.execute(
        select(Task).where(Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]))
        .order_by(Task.created_at.desc()).limit(100)
    )
    tasks = list(result.scalars().all())
    task_data = [{
        "id": t.id, "title": t.title, "status": t.status.value,
        "priority": t.priority.value, "assignee": t.assignee_name or "Unassigned",
        "due_date": t.due_date.isoformat() if t.due_date else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "category": t.category,
    } for t in tasks]
    workload = {}
    if body.include_workload:
        for t in tasks:
            name = t.assignee_name or "Unassigned"
            if name not in workload:
                workload[name] = {"total": 0, "high_priority": 0, "overdue": 0}
            workload[name]["total"] += 1
            if t.priority.value in ("high", "urgent"):
                workload[name]["high_priority"] += 1
            if t.due_date and t.due_date < datetime.now(timezone.utc) and t.status != TaskStatus.DONE:
                workload[name]["overdue"] += 1
    prioritization = await ai_engine.prioritize_tasks(task_data, workload)
    return prioritization


# ─── AI Chat ───
class ChatRequest(BaseModel):
    message: str
    context: Optional[str] = None
    history: Optional[list] = None


@limiter.limit("30/minute")
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

@limiter.limit("30/minute")
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


@limiter.limit("30/minute")
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


@limiter.limit("30/minute")
@router.post("/mom/execute")
async def mom_execute(request: Request, 
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
