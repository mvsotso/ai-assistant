"""
Task Management Service — CRUD and business logic for tasks.
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.models.task import Task, TaskStatus, TaskPriority


class TaskService:
    """Handles task CRUD operations and queries."""

    @staticmethod
    async def create_task(
        db: AsyncSession,
        title: str,
        creator_id: int,
        creator_name: str = None,
        description: str = None,
        priority: TaskPriority = TaskPriority.MEDIUM,
        assignee_id: int = None,
        assignee_name: str = None,
        due_date: datetime = None,
        source_chat_id: int = None,
        source_message_id: int = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            title=title,
            description=description,
            priority=priority,
            creator_id=creator_id,
            creator_name=creator_name,
            assignee_id=assignee_id or creator_id,
            assignee_name=assignee_name or creator_name,
            due_date=due_date,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
        )
        db.add(task)
        await db.flush()
        await db.refresh(task)
        return task

    @staticmethod
    async def get_tasks(
        db: AsyncSession,
        user_id: int = None,
        status: TaskStatus = None,
        limit: int = 20,
    ) -> list[Task]:
        """Retrieve tasks with optional filters."""
        query = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if user_id:
            query = query.where(Task.assignee_id == user_id)
        if status:
            query = query.where(Task.status == status)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_task_by_id(db: AsyncSession, task_id: int) -> Task | None:
        """Get a single task by ID."""
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def update_status(db: AsyncSession, task_id: int, status: TaskStatus) -> Task | None:
        """Update task status."""
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            task.status = status
            if status == TaskStatus.DONE:
                task.completed_at = datetime.now(timezone.utc)
            await db.flush()
            await db.refresh(task)
        return task

    @staticmethod
    async def assign_task(db: AsyncSession, task_id: int, assignee_id: int, assignee_name: str) -> Task | None:
        """Assign a task to a team member."""
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            task.assignee_id = assignee_id
            task.assignee_name = assignee_name
            await db.flush()
            await db.refresh(task)
        return task

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: int) -> bool:
        """Delete a task."""
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            await db.delete(task)
            return True
        return False

    @staticmethod
    async def get_team_stats(db: AsyncSession) -> dict:
        """Get aggregated team task statistics."""
        result = await db.execute(
            select(
                Task.assignee_name,
                Task.status,
                func.count(Task.id),
            ).group_by(Task.assignee_name, Task.status)
        )
        rows = result.all()
        stats = {}
        for name, status, count in rows:
            if name not in stats:
                stats[name] = {"todo": 0, "in_progress": 0, "review": 0, "done": 0}
            stats[name][status.value] = count
        return stats


task_service = TaskService()
