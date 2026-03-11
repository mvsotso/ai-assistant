"""
Time Tracking API - timer, manual logging, and timesheets.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.api.auth import require_auth
from app.services.time_svc import time_service

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.redis_url)

router = APIRouter(prefix="/api/v1", tags=["time-tracking"])


def _log_to_dict(log) -> dict:
    return {
        "id": log.id,
        "task_id": log.task_id,
        "user_email": log.user_email,
        "description": log.description,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "ended_at": log.ended_at.isoformat() if log.ended_at else None,
        "duration_minutes": log.duration_minutes,
        "is_running": log.is_running,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


class ManualTimeLog(BaseModel):
    minutes: float
    description: Optional[str] = None


@limiter.limit("20/minute")
@router.post("/tasks/{task_id}/timer/start")
async def start_timer(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Start a timer for a task."""
    timer = await time_service.start_timer(db, task_id, _auth.get("email", ""))
    await db.commit()
    return _log_to_dict(timer)


@limiter.limit("20/minute")
@router.post("/tasks/{task_id}/timer/stop")
async def stop_timer(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Stop the running timer for a task."""
    timer = await time_service.stop_timer(db, task_id, _auth.get("email", ""))
    if not timer:
        raise HTTPException(status_code=404, detail="No running timer found")
    await db.commit()
    return _log_to_dict(timer)


@limiter.limit("20/minute")
@router.post("/tasks/{task_id}/time")
async def log_time(
    request: Request, task_id: int, body: ManualTimeLog,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Manually log time for a task."""
    log = await time_service.log_time(
        db, task_id, _auth.get("email", ""),
        body.minutes, body.description,
    )
    await db.commit()
    return _log_to_dict(log)


@limiter.limit("30/minute")
@router.get("/tasks/{task_id}/time")
async def get_task_time(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get time logs and summary for a task."""
    logs = await time_service.get_task_time_logs(db, task_id)
    summary = await time_service.get_task_time_summary(db, task_id)
    return {
        "logs": [_log_to_dict(l) for l in logs],
        "summary": summary,
    }


@limiter.limit("30/minute")
@router.get("/timesheet")
async def get_timesheet(
    request: Request,
    start: Optional[str] = None,
    end: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get timesheet grouped by day."""
    user_email = _auth.get("email", "")
    data = await time_service.get_timesheet(db, user_email, start, end)
    # Get running timer
    running = await time_service.get_running_timer(db, user_email)
    return {"timesheet": data, "running_timer": running}


@limiter.limit("10/minute")
@router.delete("/time/{log_id}")
async def delete_time_log(
    request: Request, log_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Delete a time log entry."""
    success = await time_service.delete_log(db, log_id)
    if not success:
        raise HTTPException(status_code=404, detail="Time log not found")
    await db.commit()
    return {"ok": True, "deleted": log_id}
