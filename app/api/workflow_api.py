"""
Workflow API - automation rules CRUD and AI suggestions.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.api.auth import require_auth
from app.models.workflow_rule import WorkflowRule
from app.services.workflow_svc import workflow_service

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.redis_url)

router = APIRouter(prefix="/api/v1", tags=["workflows"])


class WorkflowCreate(BaseModel):
    name: str
    trigger: str
    condition: Optional[dict] = None
    action_type: str
    action_config: Optional[dict] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    trigger: Optional[str] = None
    condition: Optional[dict] = None
    action_type: Optional[str] = None
    action_config: Optional[dict] = None
    is_active: Optional[bool] = None


def _rule_to_dict(r: WorkflowRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "trigger": r.trigger,
        "condition": json.loads(r.condition_json) if r.condition_json else {},
        "action_type": r.action_type,
        "action_config": json.loads(r.action_config_json) if r.action_config_json else {},
        "is_active": r.is_active,
        "creator_email": r.creator_email,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@limiter.limit("30/minute")
@router.get("/workflows")
async def list_workflows(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    result = await db.execute(select(WorkflowRule).order_by(desc(WorkflowRule.created_at)))
    rules = list(result.scalars().all())
    return {"workflows": [_rule_to_dict(r) for r in rules]}


@limiter.limit("15/minute")
@router.post("/workflows")
async def create_workflow(
    request: Request,
    body: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    rule = WorkflowRule(
        name=body.name,
        trigger=body.trigger,
        condition_json=json.dumps(body.condition) if body.condition else None,
        action_type=body.action_type,
        action_config_json=json.dumps(body.action_config) if body.action_config else None,
        creator_email=_auth.get("email", ""),
    )
    db.add(rule)
    await db.flush()
    await db.refresh(rule)
    await db.commit()
    return _rule_to_dict(rule)


@limiter.limit("15/minute")
@router.patch("/workflows/{rule_id}")
async def update_workflow(
    request: Request,
    rule_id: int,
    body: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    result = await db.execute(select(WorkflowRule).where(WorkflowRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Workflow rule not found")

    if body.name is not None:
        rule.name = body.name
    if body.trigger is not None:
        rule.trigger = body.trigger
    if body.condition is not None:
        rule.condition_json = json.dumps(body.condition)
    if body.action_type is not None:
        rule.action_type = body.action_type
    if body.action_config is not None:
        rule.action_config_json = json.dumps(body.action_config)
    if body.is_active is not None:
        rule.is_active = body.is_active

    await db.commit()
    await db.refresh(rule)
    return _rule_to_dict(rule)


@limiter.limit("10/minute")
@router.delete("/workflows/{rule_id}")
async def delete_workflow(
    request: Request,
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    result = await db.execute(select(WorkflowRule).where(WorkflowRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Workflow rule not found")
    await db.delete(rule)
    await db.commit()
    return {"ok": True, "deleted": rule_id}


class SuggestRequest(BaseModel):
    title: str
    category: Optional[str] = None
    priority: str = "medium"


@limiter.limit("10/minute")
@router.post("/ai/suggest-assignee")
async def suggest_assignee(
    request: Request,
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """AI-powered assignee suggestion."""
    from app.models.task import Task, TaskPriority
    task = Task(title=body.title, category=body.category, creator_id=0)
    try:
        task.priority = TaskPriority(body.priority)
    except ValueError:
        task.priority = TaskPriority.MEDIUM
    suggestion = await workflow_service.auto_assign_ai(db, task)
    return {"suggested_assignee": suggestion}


@limiter.limit("10/minute")
@router.post("/ai/suggest-deadline")
async def suggest_deadline(
    request: Request,
    body: SuggestRequest,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """AI-powered deadline suggestion."""
    from app.models.task import Task, TaskPriority
    task = Task(title=body.title, category=body.category, creator_id=0)
    try:
        task.priority = TaskPriority(body.priority)
    except ValueError:
        task.priority = TaskPriority.MEDIUM
    suggestion = await workflow_service.suggest_deadline_ai(db, task)
    return {"suggested_deadline": suggestion}
