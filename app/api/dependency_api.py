"""
Task Dependencies API — blocks/blocked-by relationships between tasks.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.models.task import Task
from app.models.task_dependency import TaskDependency

router = APIRouter(prefix="/api/v1/tasks", tags=["Task Dependencies"])


class DependencyCreate(BaseModel):
    depends_on_id: int  # The task that must be done first


class DependencyResponse(BaseModel):
    id: int
    task_id: int
    depends_on_id: int
    dep_type: str


def _dep_task_dict(t: Task) -> dict:
    """Minimal task info for dependency display."""
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status.value,
        "priority": t.priority.value,
        "assignee": t.assignee_name,
    }


@router.get("/{task_id}/dependencies")
async def get_task_dependencies(task_id: int, db: AsyncSession = Depends(get_db)):
    """
    Get all dependencies for a task.
    Returns:
      - blocked_by: tasks that must be completed before this task
      - blocking: tasks that this task is blocking
    """
    task = await db.execute(select(Task).where(Task.id == task_id))
    if not task.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    # Tasks this task depends on (blocked by)
    blocked_by_q = await db.execute(
        select(TaskDependency, Task)
        .join(Task, Task.id == TaskDependency.depends_on_id)
        .where(TaskDependency.task_id == task_id)
    )
    blocked_by = []
    for dep, t in blocked_by_q.all():
        info = _dep_task_dict(t)
        info["dep_id"] = dep.id
        blocked_by.append(info)

    # Tasks that depend on this task (this task is blocking them)
    blocking_q = await db.execute(
        select(TaskDependency, Task)
        .join(Task, Task.id == TaskDependency.task_id)
        .where(TaskDependency.depends_on_id == task_id)
    )
    blocking = []
    for dep, t in blocking_q.all():
        info = _dep_task_dict(t)
        info["dep_id"] = dep.id
        blocking.append(info)

    # Is this task currently blocked? (any non-done dependency)
    is_blocked = any(b["status"] != "done" for b in blocked_by)

    return {
        "task_id": task_id,
        "blocked_by": blocked_by,
        "blocking": blocking,
        "is_blocked": is_blocked,
        "blocked_by_count": len(blocked_by),
        "blocking_count": len(blocking),
    }


@router.post("/{task_id}/dependencies")
async def add_dependency(task_id: int, body: DependencyCreate, db: AsyncSession = Depends(get_db)):
    """
    Add a dependency: task_id depends on (is blocked by) depends_on_id.
    The depends_on task must be completed before task_id can proceed.
    """
    if task_id == body.depends_on_id:
        raise HTTPException(status_code=400, detail="A task cannot depend on itself")

    # Verify both tasks exist
    task = await db.execute(select(Task).where(Task.id == task_id))
    if not task.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Task not found")

    dep_task = await db.execute(select(Task).where(Task.id == body.depends_on_id))
    if not dep_task.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Dependency task not found")

    # Check for duplicate
    existing = await db.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == task_id,
            TaskDependency.depends_on_id == body.depends_on_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Dependency already exists")

    # Check for circular dependency (depends_on_id should not already depend on task_id)
    reverse = await db.execute(
        select(TaskDependency).where(
            TaskDependency.task_id == body.depends_on_id,
            TaskDependency.depends_on_id == task_id,
        )
    )
    if reverse.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Circular dependency detected")

    # Also check deeper circular chains (up to 10 levels)
    visited = {task_id}
    queue = [body.depends_on_id]
    depth = 0
    while queue and depth < 10:
        current = queue.pop(0)
        if current in visited:
            raise HTTPException(status_code=400, detail="Circular dependency chain detected")
        visited.add(current)
        # Get what current depends on
        chain = await db.execute(
            select(TaskDependency.depends_on_id).where(TaskDependency.task_id == current)
        )
        for row in chain.all():
            queue.append(row[0])
        depth += 1

    dep = TaskDependency(task_id=task_id, depends_on_id=body.depends_on_id)
    db.add(dep)
    await db.flush()
    await db.refresh(dep)

    return {"id": dep.id, "task_id": task_id, "depends_on_id": body.depends_on_id, "dep_type": dep.dep_type}


@router.delete("/{task_id}/dependencies/{dep_id}")
async def remove_dependency(task_id: int, dep_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a dependency link."""
    result = await db.execute(
        select(TaskDependency).where(
            TaskDependency.id == dep_id,
            or_(TaskDependency.task_id == task_id, TaskDependency.depends_on_id == task_id),
        )
    )
    dep = result.scalar_one_or_none()
    if not dep:
        raise HTTPException(status_code=404, detail="Dependency not found")

    await db.delete(dep)
    return {"deleted": True}


@router.get("/dependency-map")
async def get_dependency_map(db: AsyncSession = Depends(get_db)):
    """
    Get a map of all task dependencies for batch display.
    Returns: { task_id: { blocked_by_count, blocking_count, is_blocked } }
    """
    all_deps = await db.execute(select(TaskDependency))
    deps = list(all_deps.scalars().all())

    # Get status of all involved tasks
    task_ids = set()
    for d in deps:
        task_ids.add(d.task_id)
        task_ids.add(d.depends_on_id)

    if not task_ids:
        return {"dep_map": {}}

    tasks_q = await db.execute(select(Task.id, Task.status).where(Task.id.in_(task_ids)))
    status_map = {tid: status.value for tid, status in tasks_q.all()}

    dep_map = {}
    for d in deps:
        # For the blocked task
        if d.task_id not in dep_map:
            dep_map[d.task_id] = {"blocked_by": 0, "blocking": 0, "is_blocked": False, "blocked_by_ids": [], "blocking_ids": []}
        dep_map[d.task_id]["blocked_by"] += 1
        dep_map[d.task_id]["blocked_by_ids"].append(d.depends_on_id)
        if status_map.get(d.depends_on_id) != "done":
            dep_map[d.task_id]["is_blocked"] = True

        # For the blocking task
        if d.depends_on_id not in dep_map:
            dep_map[d.depends_on_id] = {"blocked_by": 0, "blocking": 0, "is_blocked": False, "blocked_by_ids": [], "blocking_ids": []}
        dep_map[d.depends_on_id]["blocking"] += 1
        dep_map[d.depends_on_id]["blocking_ids"].append(d.task_id)

    return {"dep_map": dep_map}
