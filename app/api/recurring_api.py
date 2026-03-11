"""
Recurring Tasks API — CRUD for recurring task templates.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.core.database import get_db
from app.core.config import get_settings
from app.models.recurring_task import RecurringTask, RecurrenceType
from app.api.auth import verify_session_token, require_auth

settings = get_settings()
recurring_router = APIRouter(prefix="/api/v1/recurring", dependencies=[Depends(require_auth)])

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings as _gs
_limiter = Limiter(key_func=get_remote_address, storage_uri=_gs().redis_url)

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _rt_to_dict(rt: RecurringTask) -> dict:
    return {
        "id": rt.id,
        "title": rt.title,
        "description": rt.description,
        "priority": rt.priority,
        "category": rt.category,
        "subcategory": rt.subcategory,
        "assignee": rt.assignee_name,
        "recurrence": rt.recurrence.value if rt.recurrence else None,
        "day_of_week": rt.day_of_week,
        "day_of_month": rt.day_of_month,
        "month_of_year": rt.month_of_year,
        "quarter_months": rt.quarter_months,
        "semi_months": rt.semi_months,
        "time_of_day": rt.time_of_day,
        "is_active": rt.is_active,
        "last_generated": rt.last_generated.isoformat() if rt.last_generated else None,
        "next_due": rt.next_due.isoformat() if rt.next_due else None,
        "created_at": rt.created_at.isoformat() if rt.created_at else None,
        "schedule_display": _schedule_display(rt),
    }


def _schedule_display(rt: RecurringTask) -> str:
    """Human-readable schedule description."""
    r = rt.recurrence.value if rt.recurrence else ""
    if r == "daily":
        return "Every day"
    elif r == "weekly":
        day = WEEKDAYS[rt.day_of_week] if rt.day_of_week is not None and 0 <= rt.day_of_week <= 6 else "?"
        return f"Every {day}"
    elif r == "monthly":
        return f"Monthly on day {rt.day_of_month or 1}"
    elif r == "quarterly":
        return f"Quarterly on day {rt.day_of_month or 1}"
    elif r == "semi_annually":
        return f"Every 6 months on day {rt.day_of_month or 1}"
    elif r == "yearly":
        return f"Yearly on month {rt.month_of_year or 1}, day {rt.day_of_month or 1}"
    return r


class RecurringTaskCreate(BaseModel):
    title: str
    description: Optional[str] = None
    priority: str = "medium"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignee_name: Optional[str] = None
    recurrence: str  # daily, weekly, monthly, quarterly, semi_annually, yearly
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    month_of_year: Optional[int] = None
    quarter_months: Optional[str] = None
    semi_months: Optional[str] = None
    time_of_day: Optional[str] = None
    is_active: bool = True


class RecurringTaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignee_name: Optional[str] = None
    recurrence: Optional[str] = None
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    month_of_year: Optional[int] = None
    quarter_months: Optional[str] = None
    semi_months: Optional[str] = None
    time_of_day: Optional[str] = None
    is_active: Optional[bool] = None


@_limiter.limit("60/minute")
@recurring_router.get("")
async def list_recurring_tasks(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RecurringTask).order_by(desc(RecurringTask.created_at))
    )
    tasks = result.scalars().all()
    return {"recurring_tasks": [_rt_to_dict(t) for t in tasks]}


@_limiter.limit("60/minute")
@recurring_router.get("/{task_id}")
async def get_recurring_task(request: Request, task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Recurring task not found")
    return {"recurring_task": _rt_to_dict(task)}


@_limiter.limit("30/minute")
@recurring_router.post("")
async def create_recurring_task(request: Request, body: RecurringTaskCreate, db: AsyncSession = Depends(get_db)):
    # Set defaults based on recurrence type
    quarter_months = body.quarter_months
    semi_months = body.semi_months
    if body.recurrence == "quarterly" and not quarter_months:
        quarter_months = "1,4,7,10"
    if body.recurrence == "semi_annually" and not semi_months:
        semi_months = "1,7"

    rt = RecurringTask(
        title=body.title,
        description=body.description,
        priority=body.priority,
        category=body.category,
        subcategory=body.subcategory,
        assignee_name=body.assignee_name,
        recurrence=RecurrenceType(body.recurrence),
        day_of_week=body.day_of_week,
        day_of_month=body.day_of_month or 1,
        month_of_year=body.month_of_year,
        quarter_months=quarter_months,
        semi_months=semi_months,
        time_of_day=body.time_of_day or "09:00",
        is_active=body.is_active,
        creator_id=int(settings.admin_telegram_id) if settings.admin_telegram_id else 0,
        creator_name="Sot So",
        next_due=_calc_next_due(body.recurrence, body.day_of_week, body.day_of_month or 1,
                                body.month_of_year, quarter_months, semi_months),
    )
    db.add(rt)
    await db.commit()
    await db.refresh(rt)
    return {"recurring_task": _rt_to_dict(rt)}


@_limiter.limit("30/minute")
@recurring_router.patch("/{task_id}")
async def update_recurring_task(request: Request, task_id: int, body: RecurringTaskUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Not found")

    for field, value in body.dict(exclude_unset=True).items():
        if field == "recurrence" and value:
            setattr(task, field, RecurrenceType(value))
        else:
            setattr(task, field, value)

    # Recalculate next_due
    task.next_due = _calc_next_due(
        task.recurrence.value, task.day_of_week, task.day_of_month,
        task.month_of_year, task.quarter_months, task.semi_months,
    )
    await db.commit()
    await db.refresh(task)
    return {"recurring_task": _rt_to_dict(task)}


@_limiter.limit("30/minute")
@recurring_router.delete("/{task_id}")
async def delete_recurring_task(request: Request, task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(task)
    await db.commit()
    return {"deleted": True, "id": task_id}


@_limiter.limit("30/minute")
@recurring_router.post("/{task_id}/toggle")
async def toggle_recurring_task(request: Request, task_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RecurringTask).where(RecurringTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    task.is_active = not task.is_active
    await db.commit()
    return {"id": task_id, "is_active": task.is_active}


def _calc_next_due(recurrence, day_of_week, day_of_month, month_of_year, quarter_months, semi_months):
    """Calculate the next due date based on recurrence pattern."""
    from datetime import date
    now = datetime.now(timezone.utc)
    today = now.date()

    try:
        if recurrence == "daily":
            # Tomorrow
            return datetime(today.year, today.month, today.day, 9, 0, tzinfo=timezone.utc) + timedelta(days=1)

        elif recurrence == "weekly":
            dow = day_of_week if day_of_week is not None else 0
            days_ahead = dow - today.weekday()
            if days_ahead <= 0:
                days_ahead += 7
            next_date = today + timedelta(days=days_ahead)
            return datetime(next_date.year, next_date.month, next_date.day, 9, 0, tzinfo=timezone.utc)

        elif recurrence == "monthly":
            dom = min(day_of_month or 1, 28)
            if today.day >= dom:
                # Next month
                if today.month == 12:
                    next_date = date(today.year + 1, 1, dom)
                else:
                    next_date = date(today.year, today.month + 1, dom)
            else:
                next_date = date(today.year, today.month, dom)
            return datetime(next_date.year, next_date.month, next_date.day, 9, 0, tzinfo=timezone.utc)

        elif recurrence == "quarterly":
            months = [int(m) for m in (quarter_months or "1,4,7,10").split(",")]
            dom = min(day_of_month or 1, 28)
            for m in sorted(months):
                if m > today.month or (m == today.month and today.day < dom):
                    return datetime(today.year, m, dom, 9, 0, tzinfo=timezone.utc)
            # Next year first quarter month
            return datetime(today.year + 1, months[0], dom, 9, 0, tzinfo=timezone.utc)

        elif recurrence == "semi_annually":
            months = [int(m) for m in (semi_months or "1,7").split(",")]
            dom = min(day_of_month or 1, 28)
            for m in sorted(months):
                if m > today.month or (m == today.month and today.day < dom):
                    return datetime(today.year, m, dom, 9, 0, tzinfo=timezone.utc)
            return datetime(today.year + 1, months[0], dom, 9, 0, tzinfo=timezone.utc)

        elif recurrence == "yearly":
            mom = month_of_year or 1
            dom = min(day_of_month or 1, 28)
            if today.month > mom or (today.month == mom and today.day >= dom):
                return datetime(today.year + 1, mom, dom, 9, 0, tzinfo=timezone.utc)
            return datetime(today.year, mom, dom, 9, 0, tzinfo=timezone.utc)

    except Exception:
        return now + timedelta(days=1)

    return now + timedelta(days=1)
