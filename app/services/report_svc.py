"""
Report Service - generates, exports, and schedules reports.
"""
import io
import csv
import json
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sqlfunc

from app.models.task import Task, TaskStatus, TaskPriority
from app.models.saved_report import SavedReport

logger = logging.getLogger(__name__)


class ReportService:

    async def generate_report(self, db: AsyncSession, report_type: str, filters: dict = None) -> dict:
        """Generate report data based on type and filters."""
        filters = filters or {}
        dt_start = None
        dt_end = None
        if filters.get("start_date"):
            try:
                dt_start = datetime.fromisoformat(filters["start_date"].replace("Z", "+00:00"))
            except ValueError:
                pass
        if filters.get("end_date"):
            try:
                dt_end = datetime.fromisoformat(filters["end_date"].replace("Z", "+00:00"))
                if dt_end.hour == 0 and dt_end.minute == 0:
                    dt_end = dt_end + timedelta(days=1)
            except ValueError:
                pass

        query = select(Task).order_by(Task.created_at.desc())
        if dt_start:
            query = query.where(Task.created_at >= dt_start)
        if dt_end:
            query = query.where(Task.created_at <= dt_end)
        if filters.get("category"):
            query = query.where(Task.category == filters["category"])
        if filters.get("assignee"):
            query = query.where(Task.assignee_name == filters["assignee"])
        if filters.get("group_id"):
            query = query.where(Task.group_id == int(filters["group_id"]))

        result = await db.execute(query.limit(500))
        tasks = list(result.scalars().all())

        if report_type == "status_summary":
            return self._status_summary(tasks)
        elif report_type == "team_workload":
            return self._team_workload(tasks)
        elif report_type == "completion_trend":
            return self._completion_trend(tasks, int(filters.get("days", 14)))
        elif report_type == "category_breakdown":
            return self._category_breakdown(tasks)
        else:
            return self._status_summary(tasks)

    def _status_summary(self, tasks: list) -> dict:
        """Status distribution summary."""
        todo = sum(1 for t in tasks if t.status == TaskStatus.TODO)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        review = sum(1 for t in tasks if t.status == TaskStatus.REVIEW)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        now = datetime.now(timezone.utc)
        overdue = sum(1 for t in tasks if t.due_date and t.due_date < now and t.status != TaskStatus.DONE)
        completed = [t for t in tasks if t.status == TaskStatus.DONE and t.completed_at]
        avg_days = 0
        if completed:
            total_d = sum((t.completed_at - t.created_at).total_seconds() / 86400 for t in completed if t.created_at)
            avg_days = round(total_d / len(completed), 1)
        on_time = sum(1 for t in completed if t.due_date and t.completed_at <= t.due_date)
        on_time_pct = round(on_time / len(completed) * 100) if completed else 0

        rows = [
            {"metric": "Total Tasks", "value": str(len(tasks))},
            {"metric": "To Do", "value": str(todo)},
            {"metric": "In Progress", "value": str(in_progress)},
            {"metric": "In Review", "value": str(review)},
            {"metric": "Done", "value": str(done)},
            {"metric": "Overdue", "value": str(overdue)},
            {"metric": "Avg Completion (days)", "value": str(avg_days)},
            {"metric": "On-Time Rate", "value": f"{on_time_pct}%"},
        ]
        return {
            "title": "Status Summary Report",
            "type": "status_summary",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "columns": ["metric", "value"],
            "rows": rows,
            "summary": {
                "total": len(tasks), "todo": todo, "in_progress": in_progress,
                "review": review, "done": done, "overdue": overdue,
                "avg_days": avg_days, "on_time_pct": on_time_pct,
            },
        }

    def _team_workload(self, tasks: list) -> dict:
        """Team workload distribution."""
        team = {}
        for t in tasks:
            name = t.assignee_name or "Unassigned"
            if name not in team:
                team[name] = {"todo": 0, "in_progress": 0, "review": 0, "done": 0, "total": 0}
            team[name][t.status.value] = team[name].get(t.status.value, 0) + 1
            team[name]["total"] += 1

        rows = []
        for name, stats in sorted(team.items(), key=lambda x: x[1]["total"], reverse=True):
            rate = round(stats["done"] / stats["total"] * 100) if stats["total"] > 0 else 0
            rows.append({
                "assignee": name, "total": str(stats["total"]),
                "todo": str(stats["todo"]), "in_progress": str(stats["in_progress"]),
                "review": str(stats["review"]), "done": str(stats["done"]),
                "completion_rate": f"{rate}%",
            })
        return {
            "title": "Team Workload Report", "type": "team_workload",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "columns": ["assignee", "total", "todo", "in_progress", "review", "done", "completion_rate"],
            "rows": rows,
        }

    def _completion_trend(self, tasks: list, days: int = 14) -> dict:
        """Daily completion trend."""
        now = datetime.now(timezone.utc)
        trend = []
        for i in range(days - 1, -1, -1):
            day = (now - timedelta(days=i)).date()
            day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
            day_end = day_start + timedelta(days=1)
            completed = sum(1 for t in tasks if t.completed_at and day_start <= t.completed_at < day_end)
            created = sum(1 for t in tasks if t.created_at and day_start <= t.created_at < day_end)
            trend.append({"date": day.isoformat(), "completed": str(completed), "created": str(created)})
        return {
            "title": "Completion Trend Report", "type": "completion_trend",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "columns": ["date", "completed", "created"], "rows": trend,
        }

    def _category_breakdown(self, tasks: list) -> dict:
        """Category distribution."""
        cats = {}
        for t in tasks:
            cat = t.category or "Uncategorized"
            if cat not in cats:
                cats[cat] = {"total": 0, "done": 0, "in_progress": 0, "todo": 0, "review": 0}
            cats[cat]["total"] += 1
            cats[cat][t.status.value] = cats[cat].get(t.status.value, 0) + 1

        rows = []
        for cat, stats in sorted(cats.items(), key=lambda x: x[1]["total"], reverse=True):
            rows.append({
                "category": cat, "total": str(stats["total"]),
                "done": str(stats["done"]), "in_progress": str(stats["in_progress"]),
                "todo": str(stats["todo"]), "review": str(stats["review"]),
            })
        return {
            "title": "Category Breakdown Report", "type": "category_breakdown",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "columns": ["category", "total", "done", "in_progress", "todo", "review"],
            "rows": rows,
        }

    def export_csv(self, report_data: dict) -> str:
        """Export report data as CSV string."""
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=report_data.get("columns", []))
        writer.writeheader()
        for row in report_data.get("rows", []):
            writer.writerow(row)
        return output.getvalue()

    def export_html(self, report_data: dict) -> str:
        """Export report as simple HTML table for email."""
        title = report_data.get("title", "Report")
        cols = report_data.get("columns", [])
        rows = report_data.get("rows", [])
        generated = report_data.get("generated_at", "")
        html = f'<html><body><h2>{title}</h2><p>Generated: {generated}</p>'
        html += '<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-family:sans-serif;">'
        html += '<tr style="background:#f1f5f9;">'
        for col in cols:
            html += f'<th>{col.replace("_", " ").title()}</th>'
        html += '</tr>'
        for row in rows:
            html += '<tr>'
            for col in cols:
                html += f'<td>{row.get(col, "")}</td>'
            html += '</tr>'
        html += '</table></body></html>'
        return html


report_service = ReportService()
