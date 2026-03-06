"""
Task Management Service — Phase 3: Full team collaboration.
CRUD, assignments, board view, progress tracking, daily/weekly reports.
"""
from sqlalchemy import select, func, case, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone, date
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.comment import TaskComment
from app.models.user import User


class TaskService:
    """Handles task CRUD, team collaboration, and reporting."""

    # ─── CRUD ───

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
        label: str = None,
        source_chat_id: int = None,
        source_message_id: int = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            title=title,
            description=description,
            priority=priority,
            label=label,
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
    async def get_task_by_id(db: AsyncSession, task_id: int) -> Task | None:
        result = await db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_tasks(
        db: AsyncSession,
        user_id: int = None,
        status: TaskStatus = None,
        priority: TaskPriority = None,
        label: str = None,
        assignee_name: str = None,
        exclude_done: bool = False,
        limit: int = 50,
    ) -> list[Task]:
        """Retrieve tasks with flexible filters."""
        query = select(Task).order_by(Task.created_at.desc()).limit(limit)
        if user_id:
            query = query.where(Task.assignee_id == user_id)
        if assignee_name:
            query = query.where(Task.assignee_name == assignee_name)
        if status:
            query = query.where(Task.status == status)
        if priority:
            query = query.where(Task.priority == priority)
        if label:
            query = query.where(Task.label == label)
        if exclude_done:
            query = query.where(Task.status != TaskStatus.DONE)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_all_tasks(db: AsyncSession, exclude_done: bool = False, limit: int = 100) -> list[Task]:
        """Get all team tasks."""
        query = select(Task).order_by(Task.priority.desc(), Task.created_at.desc()).limit(limit)
        if exclude_done:
            query = query.where(Task.status != TaskStatus.DONE)
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_status(db: AsyncSession, task_id: int, status: TaskStatus) -> Task | None:
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            task.status = status
            if status == TaskStatus.DONE:
                task.completed_at = datetime.now(timezone.utc)
            elif task.completed_at:
                task.completed_at = None
            await db.flush()
            await db.refresh(task)
        return task

    @staticmethod
    async def update_task(
        db: AsyncSession,
        task_id: int,
        title: str = None,
        description: str = None,
        priority: TaskPriority = None,
        label: str = None,
        due_date: datetime = None,
    ) -> Task | None:
        """Update task fields."""
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            if title: task.title = title
            if description is not None: task.description = description
            if priority: task.priority = priority
            if label is not None: task.label = label
            if due_date: task.due_date = due_date
            await db.flush()
            await db.refresh(task)
        return task

    @staticmethod
    async def assign_task(db: AsyncSession, task_id: int, assignee_id: int, assignee_name: str) -> Task | None:
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            task.assignee_id = assignee_id
            task.assignee_name = assignee_name
            await db.flush()
            await db.refresh(task)
        return task

    @staticmethod
    async def delete_task(db: AsyncSession, task_id: int) -> bool:
        task = await TaskService.get_task_by_id(db, task_id)
        if task:
            await db.delete(task)
            return True
        return False

    # ─── COMMENTS ───

    @staticmethod
    async def add_comment(db: AsyncSession, task_id: int, user_id: int, user_name: str, text: str) -> TaskComment | None:
        """Add a comment to a task."""
        task = await TaskService.get_task_by_id(db, task_id)
        if not task:
            return None
        comment = TaskComment(task_id=task_id, user_id=user_id, user_name=user_name, text=text)
        db.add(comment)
        await db.flush()
        await db.refresh(comment)
        return comment

    @staticmethod
    async def get_comments(db: AsyncSession, task_id: int) -> list[TaskComment]:
        """Get all comments for a task."""
        result = await db.execute(
            select(TaskComment).where(TaskComment.task_id == task_id).order_by(TaskComment.created_at.asc())
        )
        return list(result.scalars().all())

    # ─── BOARD VIEW ───

    @staticmethod
    async def get_board(db: AsyncSession) -> dict:
        """Get task board grouped by status (Kanban style)."""
        tasks = await TaskService.get_all_tasks(db, limit=200)
        board = {
            "todo": [],
            "in_progress": [],
            "review": [],
            "done": [],
        }
        for t in tasks:
            board[t.status.value].append(t)
        return board

    # ─── TEAM STATS ───

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
            if not name:
                name = "Unassigned"
            if name not in stats:
                stats[name] = {"todo": 0, "in_progress": 0, "review": 0, "done": 0, "total": 0}
            stats[name][status.value] = count
            stats[name]["total"] += count
        return stats

    @staticmethod
    async def get_team_members(db: AsyncSession) -> list[str]:
        """Get list of all team member names with tasks."""
        result = await db.execute(
            select(Task.assignee_name).where(Task.assignee_name.isnot(None)).distinct()
        )
        return [row[0] for row in result.all()]

    # ─── OVERDUE DETECTION ───

    @staticmethod
    async def get_overdue_tasks(db: AsyncSession) -> list[Task]:
        """Get tasks that are past due date and not done."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Task).where(
                Task.due_date.isnot(None),
                Task.due_date < now,
                Task.status != TaskStatus.DONE,
            ).order_by(Task.due_date.asc())
        )
        return list(result.scalars().all())

    # ─── REPORTS ───

    @staticmethod
    async def get_daily_report_data(db: AsyncSession) -> dict:
        """Gather data for daily report."""
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        # Tasks completed today
        result = await db.execute(
            select(Task).where(Task.completed_at >= today_start, Task.status == TaskStatus.DONE)
        )
        completed_today = list(result.scalars().all())

        # All active tasks
        active = await TaskService.get_all_tasks(db, exclude_done=True)

        # Overdue
        overdue = await TaskService.get_overdue_tasks(db)

        # Team stats
        stats = await TaskService.get_team_stats(db)

        return {
            "completed_today": completed_today,
            "active_tasks": active,
            "overdue_tasks": overdue,
            "team_stats": stats,
            "todo_count": sum(s["todo"] for s in stats.values()),
            "in_progress_count": sum(s["in_progress"] for s in stats.values()),
            "review_count": sum(s["review"] for s in stats.values()),
            "done_count": sum(s["done"] for s in stats.values()),
        }

    @staticmethod
    async def get_weekly_report_data(db: AsyncSession) -> dict:
        """Gather data for weekly report."""
        week_start = datetime.now(timezone.utc) - timedelta(days=7)

        # Completed this week
        result = await db.execute(
            select(Task).where(Task.completed_at >= week_start, Task.status == TaskStatus.DONE)
        )
        completed_week = list(result.scalars().all())

        # Created this week
        result2 = await db.execute(
            select(Task).where(Task.created_at >= week_start)
        )
        created_week = list(result2.scalars().all())

        # Current active
        active = await TaskService.get_all_tasks(db, exclude_done=True)
        overdue = await TaskService.get_overdue_tasks(db)
        stats = await TaskService.get_team_stats(db)

        return {
            "completed_week": completed_week,
            "created_week": created_week,
            "active_tasks": active,
            "overdue_tasks": overdue,
            "team_stats": stats,
        }

    # ─── TASK FROM MESSAGE ───

    @staticmethod
    async def create_task_from_message(
        db: AsyncSession,
        message_text: str,
        creator_id: int,
        creator_name: str,
        chat_id: int = None,
        message_id: int = None,
    ) -> Task:
        """Create a task directly from a Telegram message (via /track reply)."""
        # Clean up the text for a task title
        title = message_text[:200].strip()
        if not title:
            title = "Task from message"
        return await TaskService.create_task(
            db,
            title=title,
            creator_id=creator_id,
            creator_name=creator_name,
            source_chat_id=chat_id,
            source_message_id=message_id,
        )


task_service = TaskService()
