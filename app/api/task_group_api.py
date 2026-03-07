"""
Task Group & Sub Group API
Full CRUD for hierarchical task categorization
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.task_group import TaskGroup, TaskSubGroup
from app.models.task import Task
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/task-groups", tags=["task-groups"])


# ── Pydantic Schemas ──

class GroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

class GroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class SubGroupCreate(BaseModel):
    name: str
    description: Optional[str] = None
    group_id: int

class SubGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class TaskGroupAssign(BaseModel):
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None

class ReorderRequest(BaseModel):
    ids: list[int]  # Ordered list of IDs


# ── Group CRUD ──

@router.get("")
async def list_groups(db: AsyncSession = Depends(get_db)):
    """List all task groups with their subgroups and task counts"""
    result = await db.execute(
        select(TaskGroup)
        .options(selectinload(TaskGroup.subgroups))
        .order_by(TaskGroup.sort_order, TaskGroup.id)
    )
    groups = result.scalars().all()

    groups_data = []
    for g in groups:
        gd = g.to_dict()
        # Get task count for this group
        count_result = await db.execute(
            select(func.count(Task.id)).where(Task.group_id == g.id)
        )
        gd["task_count"] = count_result.scalar() or 0

        # Get task count per subgroup
        for sg in gd["subgroups"]:
            sg_count = await db.execute(
                select(func.count(Task.id)).where(Task.subgroup_id == sg["id"])
            )
            sg["task_count"] = sg_count.scalar() or 0

        groups_data.append(gd)

    # Also get count of ungrouped tasks
    ungrouped = await db.execute(
        select(func.count(Task.id)).where(Task.group_id.is_(None))
    )
    ungrouped_count = ungrouped.scalar() or 0

    return {
        "groups": groups_data,
        "ungrouped_count": ungrouped_count
    }


@router.post("")
async def create_group(data: GroupCreate, db: AsyncSession = Depends(get_db)):
    """Create a new task group"""
    # Get next sort order
    max_order = await db.execute(select(func.max(TaskGroup.sort_order)))
    next_order = (max_order.scalar() or 0) + 1

    group = TaskGroup(
        name=data.name,
        description=data.description,
        icon=data.icon or "📁",
        color=data.color or "#3b82f6",
        sort_order=next_order,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)
    return group.to_dict()


@router.patch("/{group_id}")
async def update_group(group_id: int, data: GroupUpdate, db: AsyncSession = Depends(get_db)):
    """Update a task group"""
    result = await db.execute(
        select(TaskGroup).options(selectinload(TaskGroup.subgroups)).where(TaskGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(group, field, value)

    await db.commit()
    await db.refresh(group)
    return group.to_dict()


@router.delete("/{group_id}")
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a task group. Tasks in this group become ungrouped."""
    result = await db.execute(select(TaskGroup).where(TaskGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Ungroup all tasks in this group
    await db.execute(
        update(Task).where(Task.group_id == group_id).values(group_id=None, subgroup_id=None)
    )

    await db.delete(group)
    await db.commit()
    return {"ok": True, "message": f"Group '{group.name}' deleted. Tasks moved to Ungrouped."}


@router.post("/reorder")
async def reorder_groups(data: ReorderRequest, db: AsyncSession = Depends(get_db)):
    """Reorder groups by providing ordered list of IDs"""
    for idx, gid in enumerate(data.ids):
        await db.execute(
            update(TaskGroup).where(TaskGroup.id == gid).values(sort_order=idx)
        )
    await db.commit()
    return {"ok": True}


# ── SubGroup CRUD ──

@router.post("/subgroups")
async def create_subgroup(data: SubGroupCreate, db: AsyncSession = Depends(get_db)):
    """Create a subgroup under a group"""
    # Verify group exists
    grp = await db.execute(select(TaskGroup).where(TaskGroup.id == data.group_id))
    if not grp.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Parent group not found")

    max_order = await db.execute(
        select(func.max(TaskSubGroup.sort_order)).where(TaskSubGroup.group_id == data.group_id)
    )
    next_order = (max_order.scalar() or 0) + 1

    sg = TaskSubGroup(
        name=data.name,
        description=data.description,
        group_id=data.group_id,
        sort_order=next_order,
    )
    db.add(sg)
    await db.commit()
    await db.refresh(sg)
    return sg.to_dict()


@router.patch("/subgroups/{subgroup_id}")
async def update_subgroup(subgroup_id: int, data: SubGroupUpdate, db: AsyncSession = Depends(get_db)):
    """Update a subgroup"""
    result = await db.execute(select(TaskSubGroup).where(TaskSubGroup.id == subgroup_id))
    sg = result.scalar_one_or_none()
    if not sg:
        raise HTTPException(status_code=404, detail="Subgroup not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sg, field, value)

    await db.commit()
    await db.refresh(sg)
    return sg.to_dict()


@router.delete("/subgroups/{subgroup_id}")
async def delete_subgroup(subgroup_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a subgroup. Tasks keep their group but lose subgroup."""
    result = await db.execute(select(TaskSubGroup).where(TaskSubGroup.id == subgroup_id))
    sg = result.scalar_one_or_none()
    if not sg:
        raise HTTPException(status_code=404, detail="Subgroup not found")

    # Remove subgroup from tasks but keep group
    await db.execute(
        update(Task).where(Task.subgroup_id == subgroup_id).values(subgroup_id=None)
    )

    await db.delete(sg)
    await db.commit()
    return {"ok": True, "message": f"Subgroup '{sg.name}' deleted."}


@router.post("/subgroups/reorder")
async def reorder_subgroups(data: ReorderRequest, db: AsyncSession = Depends(get_db)):
    """Reorder subgroups"""
    for idx, sid in enumerate(data.ids):
        await db.execute(
            update(TaskSubGroup).where(TaskSubGroup.id == sid).values(sort_order=idx)
        )
    await db.commit()
    return {"ok": True}


# ── Task Assignment ──

@router.patch("/tasks/{task_id}/assign")
async def assign_task_group(task_id: int, data: TaskGroupAssign, db: AsyncSession = Depends(get_db)):
    """Assign or change a task's group and subgroup"""
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Validate group exists if provided
    if data.group_id is not None:
        grp = await db.execute(select(TaskGroup).where(TaskGroup.id == data.group_id))
        if not grp.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Group not found")

    # Validate subgroup belongs to group
    if data.subgroup_id is not None:
        sg = await db.execute(select(TaskSubGroup).where(TaskSubGroup.id == data.subgroup_id))
        sg_obj = sg.scalar_one_or_none()
        if not sg_obj:
            raise HTTPException(status_code=404, detail="Subgroup not found")
        if data.group_id and sg_obj.group_id != data.group_id:
            raise HTTPException(status_code=400, detail="Subgroup does not belong to the specified group")

    task.group_id = data.group_id
    task.subgroup_id = data.subgroup_id
    await db.commit()
    return {"ok": True}


# ── Bulk assign ──

class BulkAssign(BaseModel):
    task_ids: list[int]
    group_id: Optional[int] = None
    subgroup_id: Optional[int] = None

@router.post("/tasks/bulk-assign")
async def bulk_assign_tasks(data: BulkAssign, db: AsyncSession = Depends(get_db)):
    """Assign multiple tasks to a group/subgroup at once"""
    await db.execute(
        update(Task)
        .where(Task.id.in_(data.task_ids))
        .values(group_id=data.group_id, subgroup_id=data.subgroup_id)
    )
    await db.commit()
    return {"ok": True, "count": len(data.task_ids)}
