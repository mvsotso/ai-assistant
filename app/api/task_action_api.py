"""
Task Actions API — CRUD for checklist items within tasks.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.task_action import TaskAction
from app.models.task import Task, TaskStatus
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/tasks", tags=["task-actions"])


# ── Schemas ──

class ActionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[str] = None

class ActionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    assignee_name: Optional[str] = None
    due_date: Optional[str] = None
    is_done: Optional[bool] = None

class ActionReorder(BaseModel):
    ids: list[int]


# ── Get actions for a task ──

@router.get("/{task_id}/actions")
async def list_actions(task_id: int, db: AsyncSession = Depends(get_db)):
    """Get all actions for a task, ordered by sort_order."""
    result = await db.execute(
        select(TaskAction)
        .where(TaskAction.task_id == task_id)
        .order_by(TaskAction.sort_order, TaskAction.id)
    )
    actions = result.scalars().all()

    total = len(actions)
    done = sum(1 for a in actions if a.is_done)

    return {
        "actions": [a.to_dict() for a in actions],
        "total": total,
        "done": done,
        "progress": round(done / total * 100) if total > 0 else 0,
    }


# ── Create action ──

@router.post("/{task_id}/actions")
async def create_action(task_id: int, data: ActionCreate, db: AsyncSession = Depends(get_db)):
    """Add a new action to a task."""
    # Verify task exists
    task = await db.execute(select(Task).where(Task.id == task_id))
    if not task.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    # Get next sort order
    max_order = await db.execute(
        select(func.max(TaskAction.sort_order)).where(TaskAction.task_id == task_id)
    )
    next_order = (max_order.scalar() or 0) + 1

    due = None
    if data.due_date:
        try:
            due = datetime.fromisoformat(data.due_date.replace("Z", "+00:00"))
        except ValueError:
            pass

    action = TaskAction(
        task_id=task_id,
        title=data.title,
        description=data.description,
        assignee_name=data.assignee_name,
        due_date=due,
        sort_order=next_order,
    )
    db.add(action)
    await db.commit()
    await db.refresh(action)
    return action.to_dict()


# ── Update action ──

@router.patch("/{task_id}/actions/{action_id}")
async def update_action(task_id: int, action_id: int, data: ActionUpdate, db: AsyncSession = Depends(get_db)):
    """Update an action."""
    result = await db.execute(
        select(TaskAction).where(TaskAction.id == action_id, TaskAction.task_id == task_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    updates = data.model_dump(exclude_unset=True)

    if "due_date" in updates and updates["due_date"]:
        try:
            updates["due_date"] = datetime.fromisoformat(updates["due_date"].replace("Z", "+00:00"))
        except ValueError:
            del updates["due_date"]

    if "is_done" in updates:
        if updates["is_done"] and not action.is_done:
            updates["completed_at"] = datetime.now(timezone.utc)
        elif not updates["is_done"]:
            updates["completed_at"] = None

    for field, value in updates.items():
        setattr(action, field, value)

    await db.commit()
    await db.refresh(action)

    # Check if all actions are done → auto-complete task
    await _check_auto_complete(task_id, db)

    return action.to_dict()


# ── Toggle action done/undone ──

@router.post("/{task_id}/actions/{action_id}/toggle")
async def toggle_action(task_id: int, action_id: int, db: AsyncSession = Depends(get_db)):
    """Toggle an action's done status."""
    result = await db.execute(
        select(TaskAction).where(TaskAction.id == action_id, TaskAction.task_id == task_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    action.is_done = not action.is_done
    action.completed_at = datetime.now(timezone.utc) if action.is_done else None

    await db.commit()
    await db.refresh(action)

    # Check auto-complete
    await _check_auto_complete(task_id, db)

    return action.to_dict()


# ── Delete action ──

@router.delete("/{task_id}/actions/{action_id}")
async def delete_action(task_id: int, action_id: int, db: AsyncSession = Depends(get_db)):
    """Delete an action."""
    result = await db.execute(
        select(TaskAction).where(TaskAction.id == action_id, TaskAction.task_id == task_id)
    )
    action = result.scalar_one_or_none()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")

    await db.delete(action)
    await db.commit()
    return {"ok": True}


# ── Reorder actions ──

@router.post("/{task_id}/actions/reorder")
async def reorder_actions(task_id: int, data: ActionReorder, db: AsyncSession = Depends(get_db)):
    """Reorder actions by providing ordered list of IDs."""
    for idx, aid in enumerate(data.ids):
        await db.execute(
            update(TaskAction)
            .where(TaskAction.id == aid, TaskAction.task_id == task_id)
            .values(sort_order=idx)
        )
    await db.commit()
    return {"ok": True}


# ── Get action stats for multiple tasks (used by task list) ──

@router.get("/action-stats")
async def get_all_action_stats(db: AsyncSession = Depends(get_db)):
    """Get action progress stats for all tasks that have actions."""
    from sqlalchemy import case
    result = await db.execute(
        select(
            TaskAction.task_id,
            func.count(TaskAction.id).label("total"),
            func.count(case((TaskAction.is_done == True, 1))).label("done"),
        )
        .group_by(TaskAction.task_id)
    )

    stats = {}
    for row in result.all():
        tid, total, done = row
        stats[str(tid)] = {"total": total, "done": done, "progress": round(done / total * 100) if total > 0 else 0}
    return {"stats": stats}


# ── Helper: Auto-complete task when all actions done ──

async def _check_auto_complete(task_id: int, db: AsyncSession):
    """If all actions are done, mark task as done. If any undone, revert to in_progress."""
    result = await db.execute(
        select(TaskAction).where(TaskAction.task_id == task_id)
    )
    actions = result.scalars().all()
    if not actions:
        return

    all_done = all(a.is_done for a in actions)
    any_done = any(a.is_done for a in actions)

    task_result = await db.execute(select(Task).where(Task.id == task_id))
    task = task_result.scalar_one_or_none()
    if not task:
        return

    if all_done and task.status != TaskStatus.DONE:
        task.status = TaskStatus.DONE
        task.completed_at = datetime.now(timezone.utc)
    elif not all_done and task.status == TaskStatus.DONE:
        # Revert if someone unchecks an action
        task.status = TaskStatus.IN_PROGRESS
        task.completed_at = None

    await db.flush()
