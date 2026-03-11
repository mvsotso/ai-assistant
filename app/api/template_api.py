"""
Task Template API — CRUD for reusable task creation presets.
"""
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings as _gs
from app.core.database import get_db
from app.models.task_template import TaskTemplate
from app.api.auth import require_auth

logger = logging.getLogger(__name__)

_limiter = Limiter(key_func=get_remote_address, storage_uri=_gs().redis_url)

router = APIRouter(
    prefix="/api/v1/templates",
    tags=["templates"],
    dependencies=[Depends(require_auth)],
)


class ChecklistItem(BaseModel):
    title: str
    assignee_name: Optional[str] = None


class TemplateCreate(BaseModel):
    name: str
    title_template: str
    description_text: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    priority: str = "medium"
    status: str = "todo"
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignee_name: Optional[str] = None
    label: Optional[str] = None
    due_offset_hours: Optional[int] = None
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    checklist: Optional[List[ChecklistItem]] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    title_template: Optional[str] = None
    description_text: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    assignee_name: Optional[str] = None
    label: Optional[str] = None
    due_offset_hours: Optional[int] = None
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None
    checklist: Optional[List[ChecklistItem]] = None


@_limiter.limit("60/minute")
@router.get("")
async def list_templates(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(TaskTemplate)
        .where(TaskTemplate.is_active == True)
        .order_by(TaskTemplate.use_count.desc(), TaskTemplate.sort_order, TaskTemplate.id)
    )
    return {"templates": [t.to_dict() for t in result.scalars().all()]}


@_limiter.limit("60/minute")
@router.get("/{tmpl_id}")
async def get_template(request: Request, tmpl_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == tmpl_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": tmpl.to_dict()}


@_limiter.limit("30/minute")
@router.post("")
async def create_template(request: Request, data: TemplateCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(TaskTemplate).where(TaskTemplate.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Template with this name already exists")

    max_order = await db.execute(select(func.max(TaskTemplate.sort_order)))
    next_order = (max_order.scalar() or 0) + 1

    tmpl = TaskTemplate(
        name=data.name,
        title_template=data.title_template,
        description_text=data.description_text,
        icon=data.icon or "📋",
        color=data.color or "#3b82f6",
        priority=data.priority,
        status=data.status,
        category=data.category,
        subcategory=data.subcategory,
        assignee_name=data.assignee_name,
        label=data.label,
        due_offset_hours=data.due_offset_hours,
        group_id=data.group_id,
        subgroup_id=data.subgroup_id,
        checklist_json=json.dumps([c.model_dump() for c in data.checklist]) if data.checklist else None,
        sort_order=next_order,
    )
    db.add(tmpl)
    await db.flush()
    await db.refresh(tmpl)
    return tmpl.to_dict()


@_limiter.limit("30/minute")
@router.patch("/{tmpl_id}")
async def update_template(request: Request, tmpl_id: int, data: TemplateUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == tmpl_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    updates = data.model_dump(exclude_unset=True)
    if "checklist" in updates:
        cl = updates.pop("checklist")
        updates["checklist_json"] = json.dumps([c if isinstance(c, dict) else c.model_dump() for c in cl]) if cl else None

    for field, value in updates.items():
        setattr(tmpl, field, value)

    await db.flush()
    await db.refresh(tmpl)
    return tmpl.to_dict()


@_limiter.limit("30/minute")
@router.delete("/{tmpl_id}")
async def delete_template(request: Request, tmpl_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == tmpl_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    if tmpl.is_builtin:
        tmpl.is_active = False
        return {"ok": True, "message": f"Template '{tmpl.name}' deactivated."}
    await db.delete(tmpl)
    return {"ok": True, "message": f"Template '{tmpl.name}' deleted."}


@_limiter.limit("60/minute")
@router.post("/{tmpl_id}/use")
async def use_template(request: Request, tmpl_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TaskTemplate).where(TaskTemplate.id == tmpl_id))
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl.use_count = (tmpl.use_count or 0) + 1
    return {"ok": True, "use_count": tmpl.use_count}
