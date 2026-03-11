"""
Workflow Service - evaluates automation rules and executes actions.
"""
import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.models.task import Task, TaskStatus, TaskPriority
from app.models.workflow_rule import WorkflowRule

logger = logging.getLogger(__name__)


class WorkflowService:

    async def evaluate_rules(self, db: AsyncSession, trigger: str, task: Task):
        """Find matching workflow rules for a trigger and execute them."""
        result = await db.execute(
            select(WorkflowRule).where(
                WorkflowRule.is_active == True,
                WorkflowRule.trigger == trigger,
            )
        )
        rules = result.scalars().all()

        for rule in rules:
            try:
                if self._matches_condition(rule, task):
                    await self._execute_action(db, rule, task)
                    logger.info(f"Workflow rule '{rule.name}' executed for task {task.id}")
            except Exception as e:
                logger.error(f"Workflow rule {rule.id} failed: {e}")

    def _matches_condition(self, rule: WorkflowRule, task: Task) -> bool:
        """Check if task matches rule conditions."""
        if not rule.condition_json:
            return True
        try:
            conditions = json.loads(rule.condition_json)
        except (json.JSONDecodeError, TypeError):
            return True

        for key, value in conditions.items():
            if key == "priority" and task.priority and task.priority.value != value:
                return False
            if key == "category" and task.category != value:
                return False
            if key == "status" and task.status and task.status.value != value:
                return False
            if key == "assignee" and task.assignee_name != value:
                return False
        return True

    async def _execute_action(self, db: AsyncSession, rule: WorkflowRule, task: Task):
        """Execute the action defined by a workflow rule."""
        config = {}
        if rule.action_config_json:
            try:
                config = json.loads(rule.action_config_json)
            except (json.JSONDecodeError, TypeError):
                pass

        if rule.action_type == "auto_assign":
            assignee = config.get("assignee")
            if assignee:
                task.assignee_name = assignee
                logger.info(f"Auto-assigned task {task.id} to {assignee}")

        elif rule.action_type == "set_deadline":
            hours = config.get("hours", 48)
            task.due_date = datetime.now(timezone.utc) + timedelta(hours=hours)
            logger.info(f"Set deadline for task {task.id}: +{hours}h")

        elif rule.action_type == "escalate":
            new_priority = config.get("priority", "urgent")
            try:
                task.priority = TaskPriority(new_priority)
            except ValueError:
                task.priority = TaskPriority.URGENT
            # Send notification
            notify_to = config.get("notify_to")
            if notify_to:
                try:
                    from app.services.notification_svc import create_notification
                    await create_notification(
                        db, user_id=0, notif_type="task_escalated",
                        title=f"Task escalated: {task.title}",
                        entity_id=task.id, entity_type="task"
                    )
                except Exception:
                    pass
            logger.info(f"Escalated task {task.id} to {new_priority}")

        elif rule.action_type == "notify":
            try:
                from app.services.notification_svc import create_notification
                msg = config.get("message", f"Workflow triggered: {rule.name}")
                await create_notification(
                    db, user_id=0, notif_type="workflow_triggered",
                    title=msg, entity_id=task.id, entity_type="task"
                )
            except Exception:
                pass

        elif rule.action_type == "change_status":
            new_status = config.get("status", "in_progress")
            try:
                task.status = TaskStatus(new_status)
                if task.status == TaskStatus.DONE:
                    task.completed_at = datetime.now(timezone.utc)
            except ValueError:
                pass
            logger.info(f"Changed task {task.id} status to {new_status}")

    async def auto_assign_ai(self, db: AsyncSession, task: Task) -> str:
        """Use AI to suggest the best assignee based on workload and expertise."""
        from app.models.user import User
        # Get team members and their workload
        users_result = await db.execute(select(User).order_by(User.created_at.asc()))
        users = list(users_result.scalars().all())

        workload = {}
        for u in users:
            name = u.first_name or u.telegram_username or "Unknown"
            count_result = await db.execute(
                select(sqlfunc.count(Task.id)).where(
                    Task.assignee_name == name,
                    Task.status.in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW])
                )
            )
            workload[name] = count_result.scalar() or 0

        if not workload:
            return ""

        # Use AI to suggest
        try:
            from app.services.ai_engine import ai_engine
            suggestion = await ai_engine.suggest_assignee(
                task_title=task.title,
                task_category=task.category,
                task_priority=task.priority.value if task.priority else "medium",
                team_workload=workload,
            )
            return suggestion
        except Exception as e:
            logger.error(f"AI assignee suggestion failed: {e}")
            # Fallback: assign to person with least workload
            if workload:
                return min(workload, key=workload.get)
            return ""

    async def suggest_deadline_ai(self, db: AsyncSession, task: Task) -> str:
        """Use AI to suggest a deadline based on similar completed tasks."""
        # Get similar completed tasks
        similar = await db.execute(
            select(Task).where(
                Task.status == TaskStatus.DONE,
                Task.completed_at.isnot(None),
                Task.created_at.isnot(None),
            ).order_by(Task.completed_at.desc()).limit(20)
        )
        similar_tasks = list(similar.scalars().all())

        avg_days = 3  # default
        if similar_tasks:
            durations = [(t.completed_at - t.created_at).total_seconds() / 86400 for t in similar_tasks if t.created_at]
            if durations:
                avg_days = sum(durations) / len(durations)

        try:
            from app.services.ai_engine import ai_engine
            suggestion = await ai_engine.suggest_deadline(
                task_title=task.title,
                task_priority=task.priority.value if task.priority else "medium",
                avg_completion_days=round(avg_days, 1),
            )
            return suggestion
        except Exception as e:
            logger.error(f"AI deadline suggestion failed: {e}")
            # Fallback: use average
            deadline = datetime.now(timezone.utc) + timedelta(days=max(1, round(avg_days)))
            return deadline.isoformat()


workflow_service = WorkflowService()
