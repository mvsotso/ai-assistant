"""
Telegram Bot Command Handlers — Phase 3: Full team collaboration.
"""
import re
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.models.user import User
from app.models.message import Message
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.reminder import Reminder
from app.services.telegram import telegram_service
from app.services.ai_engine import ai_engine
from app.services.task_svc import task_service
from app.core.security import is_admin

logger = logging.getLogger(__name__)

TASK_KEYWORDS = re.compile(r"\b(TODO|ACTION|DEADLINE|URGENT|ASAP|FOLLOW.?UP|ASSIGNED)\b", re.IGNORECASE)

STATUS_ICONS = {"todo": "\U0001F4CB", "in_progress": "\U0001F504", "review": "\U0001F440", "done": "\u2705"}
PRIORITY_ICONS = {"low": "\U0001F7E2", "medium": "\U0001F7E1", "high": "\U0001F7E0", "urgent": "\U0001F534"}


class BotHandlers:
    """Processes Telegram updates and routes to appropriate handlers."""

    async def handle_update(self, update: dict, db: AsyncSession):
        # Handle callback queries (inline keyboard button presses)
        callback_query = update.get("callback_query")
        if callback_query:
            await self._handle_callback_query(callback_query, db)
            return

        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "") or message.get("caption", "") or ""
        user = message.get("from", {})
        user_id = user.get("id")
        user_name = user.get("first_name", "Unknown")

        # Always store messages silently (from all users)
        await self._store_message(db, message)

        # Only admin can use commands and AI chat
        if not is_admin(user_id):
            return

        if text.startswith("/"):
            await self._handle_command(db, chat_id, user_id, user_name, text, message)
        elif message["chat"]["type"] == "private":
            # Check for file attachments
            file_id = None
            file_name = "file"
            if message.get("document"):
                file_id = message["document"]["file_id"]
                file_name = message["document"].get("file_name", "document")
            elif message.get("photo"):
                # Get highest resolution photo
                file_id = message["photo"][-1]["file_id"]
                file_name = "photo.jpg"

            if file_id:
                await self._handle_file_chat(db, chat_id, user_id, user_name, text, file_id, file_name)
            elif text:
                await self._handle_ai_chat(db, chat_id, user_id, user_name, text)

    async def _store_message(self, db: AsyncSession, message: dict):
        text = message.get("text", "")
        msg = Message(
            telegram_message_id=message["message_id"],
            chat_id=message["chat"]["id"],
            chat_title=message["chat"].get("title"),
            sender_id=message["from"]["id"],
            sender_name=message["from"].get("first_name", "Unknown"),
            text=text,
            is_command=text.startswith("/"),
            has_task_keyword=bool(TASK_KEYWORDS.search(text)) if text else False,
        )
        db.add(msg)

    async def _handle_command(self, db, chat_id, user_id, user_name, text, message):
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/summary": self._cmd_summary,
            "/task": self._cmd_task,
            "/board": self._cmd_board,
            "/progress": self._cmd_progress,
            "/track": self._cmd_track,
            "/report": self._cmd_report,
            "/remind": self._cmd_remind,
            "/send": self._cmd_send,
            "/translate": self._cmd_translate,
            "/extract": self._cmd_extract,
            "/insights": self._cmd_insights,
            "/draft": self._cmd_draft,
            "/connect": self._cmd_calendar,
            "/today": self._cmd_calendar,
            "/week": self._cmd_calendar,
            "/free": self._cmd_calendar,
            "/event": self._cmd_calendar,
            "/cancel": self._cmd_calendar,
        }

        handler = handlers.get(command)
        if handler:
            await handler(db, chat_id, user_id, user_name, args, message)
        else:
            await telegram_service.send_message(chat_id, f"Unknown command: `{command}`\nType /help to see available commands.")

    # ─── GENERAL COMMANDS ───

    async def _cmd_start(self, db, chat_id, user_id, user_name, args, message):
        result = await db.execute(select(User).where(User.telegram_id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                telegram_id=user_id,
                telegram_username=message["from"].get("username"),
                first_name=user_name,
                last_name=message["from"].get("last_name"),
                is_admin=is_admin(user_id),
            )
            db.add(user)
            reg = "registered"
        else:
            reg = "already registered"

        await telegram_service.send_message(chat_id, f"""\U0001F44B *Welcome to AI Personal Assistant!*

You are {reg} as *{user_name}*.

I can help you with:
\u2022 \U0001F4AC Summarize group messages
\u2022 \u2705 Manage tasks and assignments
\u2022 \U0001F4CB View task board and team progress
\u2022 \u23F0 Set reminders
\u2022 \U0001F4C5 Check your calendar
\u2022 \U0001F916 Chat with AI for anything else

Type /help to see all commands.""")

    async def _cmd_help(self, db, chat_id, user_id, user_name, args, message):
        await telegram_service.send_message(chat_id, """\U0001F4D6 *Available Commands*

*General*
/start \u2014 Register and get started
/help \u2014 Show this help message
/status \u2014 Your task stats and system status

*Tasks*
/task add <title> \u2014 Create a new task
/task list \u2014 Show your pending tasks
/task all \u2014 Show all team tasks
/task done <id> \u2014 Mark task as completed
/task wip <id> \u2014 Set task to In Progress
/task assign <id> @user \u2014 Assign task to someone
/task priority <id> high \u2014 Set priority (low/medium/high/urgent)
/task label <id> ETL \u2014 Add a label/category
/task describe <id> <text> \u2014 Add description
/task comment <id> <text> \u2014 Add a comment
/task detail <id> \u2014 View full task details
/task delete <id> \u2014 Delete a task

*Team Collaboration*
/board \u2014 Visual task board (To Do / In Progress / Review / Done)
/progress \u2014 Team progress with completion percentages
/track \u2014 Reply to a message to create a task from it
/report \u2014 Generate team daily/weekly report (AI)

*Messages*
/summary \u2014 Summarize recent messages in this group
/send <chat\\_id> <message> \u2014 Send message on your behalf

*Calendar*
/connect \u2014 Link Google Calendar
/today \u2014 Today's schedule
/week \u2014 7-day schedule
/free \u2014 Find available time slots
/event <title> at <time> for <dur> \u2014 Create event
/cancel <name> \u2014 Cancel an event

*Reminders*
/remind <minutes> <message> \u2014 Set a reminder

*AI Chat*
Just send me any message in private chat!""")

    async def _cmd_status(self, db, chat_id, user_id, user_name, args, message):
        my_tasks = await task_service.get_tasks(db, user_id=user_id, limit=100)
        todo = sum(1 for t in my_tasks if t.status == TaskStatus.TODO)
        wip = sum(1 for t in my_tasks if t.status == TaskStatus.IN_PROGRESS)
        review = sum(1 for t in my_tasks if t.status == TaskStatus.REVIEW)
        done = sum(1 for t in my_tasks if t.status == TaskStatus.DONE)
        overdue = await task_service.get_overdue_tasks(db)
        my_overdue = [t for t in overdue if t.assignee_id == user_id]

        text = f"""\U0001F4CA *Status for {user_name}*

*Your Tasks:*
\u2022 \U0001F4CB To Do: {todo}
\u2022 \U0001F504 In Progress: {wip}
\u2022 \U0001F440 Review: {review}
\u2022 \u2705 Completed: {done}"""

        if my_overdue:
            text += f"\n\u2022 \U0001F534 Overdue: {len(my_overdue)}"

        text += "\n\n*System:* \U0001F7E2 Online\n*AI Engine:* \U0001F7E2 Ready"
        await telegram_service.send_message(chat_id, text)

    # ─── TASK COMMANDS (Enhanced) ───

    async def _cmd_task(self, db, chat_id, user_id, user_name, args, message):
        if not args:
            await telegram_service.send_message(chat_id, "Usage: `/task add|list|all|done|wip|assign|priority|label|describe|comment|detail|delete`\nType /help for full details.")
            return

        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""

        subcmds = {
            "add": self._task_add,
            "list": self._task_list,
            "all": self._task_all,
            "done": self._task_done,
            "wip": self._task_wip,
            "assign": self._task_assign,
            "priority": self._task_priority,
            "label": self._task_label,
            "describe": self._task_describe,
            "comment": self._task_comment,
            "detail": self._task_detail,
            "delete": self._task_delete,
        }

        handler = subcmds.get(subcmd)
        if handler:
            await handler(db, chat_id, user_id, user_name, subargs, message)
        else:
            await telegram_service.send_message(chat_id, f"Unknown task command: `{subcmd}`\nTry: add, list, all, done, wip, assign, priority, label, describe, comment, detail, delete")

    async def _task_add(self, db, chat_id, user_id, user_name, args, message):
        if not args:
            await telegram_service.send_message(chat_id, "Usage: `/task add <title>`")
            return
        task = await task_service.create_task(
            db, title=args, creator_id=user_id, creator_name=user_name,
            source_chat_id=chat_id, source_message_id=message["message_id"],
        )
        await telegram_service.send_message(chat_id, f"\u2705 Task *#{task.id}* created: *{task.title}*\nAssigned to: {user_name}\nSet priority: `/task priority {task.id} high`")

    async def _task_list(self, db, chat_id, user_id, user_name, args, message):
        tasks = await task_service.get_tasks(db, user_id=user_id, exclude_done=True)
        if not tasks:
            await telegram_service.send_message(chat_id, "No pending tasks! \U0001F389")
            return
        lines = [f"*Your Tasks ({len(tasks)}):*\n"]
        for t in tasks:
            icon = STATUS_ICONS.get(t.status.value, "\u2022")
            prio = PRIORITY_ICONS.get(t.priority.value, "")
            due = f" \u23F0{t.due_date.strftime('%b %d')}" if t.due_date else ""
            lbl = f" [{t.label}]" if t.label else ""
            lines.append(f"{icon}{prio} *#{t.id}* {t.title}{lbl}{due}")
        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def _task_all(self, db, chat_id, user_id, user_name, args, message):
        tasks = await task_service.get_all_tasks(db, exclude_done=True)
        if not tasks:
            await telegram_service.send_message(chat_id, "No active tasks across the team! \U0001F389")
            return
        lines = [f"*All Team Tasks ({len(tasks)}):*\n"]
        for t in tasks:
            icon = STATUS_ICONS.get(t.status.value, "\u2022")
            prio = PRIORITY_ICONS.get(t.priority.value, "")
            assignee = t.assignee_name or "Unassigned"
            due = f" \u23F0{t.due_date.strftime('%b %d')}" if t.due_date else ""
            lines.append(f"{icon}{prio} *#{t.id}* {t.title} \u2192 _{assignee}_{due}")
        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def _task_done(self, db, chat_id, user_id, user_name, args, message):
        try:
            task_id = int(args.strip())
            task = await task_service.update_status(db, task_id, TaskStatus.DONE)
            if task:
                await telegram_service.send_message(chat_id, f"\u2705 Task *#{task_id}* completed: *{task.title}*\nGreat work! \U0001F389")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        except ValueError:
            await telegram_service.send_message(chat_id, "Usage: `/task done <id>`")

    async def _task_wip(self, db, chat_id, user_id, user_name, args, message):
        try:
            task_id = int(args.strip())
            task = await task_service.update_status(db, task_id, TaskStatus.IN_PROGRESS)
            if task:
                await telegram_service.send_message(chat_id, f"\U0001F504 Task *#{task_id}* set to *In Progress*: {task.title}")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        except ValueError:
            await telegram_service.send_message(chat_id, "Usage: `/task wip <id>`")

    async def _task_assign(self, db, chat_id, user_id, user_name, args, message):
        match = re.match(r"(\d+)\s+@?(\S+)", args)
        if match:
            task_id = int(match.group(1))
            assignee = match.group(2)
            task = await task_service.assign_task(db, task_id, 0, assignee)
            if task:
                await telegram_service.send_message(chat_id, f"\U0001F464 Task *#{task_id}* assigned to *{assignee}*: {task.title}")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        else:
            await telegram_service.send_message(chat_id, "Usage: `/task assign <id> @username`")

    async def _task_priority(self, db, chat_id, user_id, user_name, args, message):
        match = re.match(r"(\d+)\s+(low|medium|high|urgent)", args, re.IGNORECASE)
        if match:
            task_id = int(match.group(1))
            priority = TaskPriority(match.group(2).lower())
            task = await task_service.update_task(db, task_id, priority=priority)
            if task:
                icon = PRIORITY_ICONS.get(priority.value, "")
                await telegram_service.send_message(chat_id, f"{icon} Task *#{task_id}* priority set to *{priority.value}*")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        else:
            await telegram_service.send_message(chat_id, "Usage: `/task priority <id> low|medium|high|urgent`")

    async def _task_label(self, db, chat_id, user_id, user_name, args, message):
        match = re.match(r"(\d+)\s+(\S+)", args)
        if match:
            task_id = int(match.group(1))
            label = match.group(2)
            task = await task_service.update_task(db, task_id, label=label)
            if task:
                await telegram_service.send_message(chat_id, f"\U0001F3F7 Task *#{task_id}* labeled *[{label}]*")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        else:
            await telegram_service.send_message(chat_id, "Usage: `/task label <id> <label>`\nExample: `/task label 3 ETL`")

    async def _task_describe(self, db, chat_id, user_id, user_name, args, message):
        match = re.match(r"(\d+)\s+(.+)", args, re.DOTALL)
        if match:
            task_id = int(match.group(1))
            desc = match.group(2).strip()
            task = await task_service.update_task(db, task_id, description=desc)
            if task:
                await telegram_service.send_message(chat_id, f"\U0001F4DD Description added to task *#{task_id}*")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        else:
            await telegram_service.send_message(chat_id, "Usage: `/task describe <id> <description text>`")

    async def _task_comment(self, db, chat_id, user_id, user_name, args, message):
        match = re.match(r"(\d+)\s+(.+)", args, re.DOTALL)
        if match:
            task_id = int(match.group(1))
            text = match.group(2).strip()
            comment = await task_service.add_comment(db, task_id, user_id, user_name, text)
            if comment:
                await telegram_service.send_message(chat_id, f"\U0001F4AC Comment added to task *#{task_id}* by {user_name}")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        else:
            await telegram_service.send_message(chat_id, "Usage: `/task comment <id> <your comment>`")

    async def _task_detail(self, db, chat_id, user_id, user_name, args, message):
        try:
            task_id = int(args.strip())
            task = await task_service.get_task_by_id(db, task_id)
            if not task:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
                return

            icon = STATUS_ICONS.get(task.status.value, "")
            prio_icon = PRIORITY_ICONS.get(task.priority.value, "")
            lines = [
                f"{icon} *Task #{task.id}: {task.title}*\n",
                f"\U0001F4CC Status: *{task.status.value.replace('_', ' ').title()}*",
                f"{prio_icon} Priority: *{task.priority.value.title()}*",
                f"\U0001F464 Assigned to: *{task.assignee_name or 'Unassigned'}*",
                f"\U0001F464 Created by: {task.creator_name or 'Unknown'}",
            ]
            if task.label:
                lines.append(f"\U0001F3F7 Label: *[{task.label}]*")
            if task.description:
                lines.append(f"\n\U0001F4DD *Description:*\n{task.description}")
            if task.due_date:
                lines.append(f"\n\u23F0 Due: {task.due_date.strftime('%B %d, %Y %I:%M %p')}")
            lines.append(f"\n\U0001F4C5 Created: {task.created_at.strftime('%B %d, %Y')}")

            # Comments
            comments = await task_service.get_comments(db, task_id)
            if comments:
                lines.append(f"\n\U0001F4AC *Comments ({len(comments)}):*")
                for c in comments[-5:]:  # Last 5 comments
                    lines.append(f"  \u2022 *{c.user_name}*: {c.text}")

            await telegram_service.send_message(chat_id, "\n".join(lines))
        except ValueError:
            await telegram_service.send_message(chat_id, "Usage: `/task detail <id>`")

    async def _task_delete(self, db, chat_id, user_id, user_name, args, message):
        try:
            task_id = int(args.strip())
            deleted = await task_service.delete_task(db, task_id)
            if deleted:
                await telegram_service.send_message(chat_id, f"\U0001F5D1 Task *#{task_id}* deleted.")
            else:
                await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
        except ValueError:
            await telegram_service.send_message(chat_id, "Usage: `/task delete <id>`")

    # ─── BOARD COMMAND ───

    async def _cmd_board(self, db, chat_id, user_id, user_name, args, message):
        board = await task_service.get_board(db)
        sections = [
            ("\U0001F4CB TO DO", board["todo"]),
            ("\U0001F504 IN PROGRESS", board["in_progress"]),
            ("\U0001F440 REVIEW", board["review"]),
            ("\u2705 DONE (recent)", board["done"][:5]),
        ]
        lines = ["\U0001F4CB *Task Board*\n"]
        for title, tasks in sections:
            lines.append(f"\n*{title}* ({len(tasks)})")
            if not tasks:
                lines.append("  _No tasks_")
            for t in tasks[:10]:
                prio = PRIORITY_ICONS.get(t.priority.value, "")
                assignee = t.assignee_name or "?"
                lines.append(f"  {prio} #{t.id} {t.title} \u2192 _{assignee}_")

        await telegram_service.send_message(chat_id, "\n".join(lines))

    # ─── PROGRESS COMMAND ───

    async def _cmd_progress(self, db, chat_id, user_id, user_name, args, message):
        stats = await task_service.get_team_stats(db)
        if not stats:
            await telegram_service.send_message(chat_id, "No tasks yet. Create one with `/task add <title>`")
            return

        lines = ["\U0001F4CA *Team Progress*\n"]
        for name, s in stats.items():
            total = s["total"]
            done = s["done"]
            pct = round((done / total) * 100) if total > 0 else 0
            bar_filled = round(pct / 10)
            bar = "\u2588" * bar_filled + "\u2591" * (10 - bar_filled)
            lines.append(f"\n*{name}*")
            lines.append(f"  {bar} {pct}% ({done}/{total})")
            details = []
            if s["todo"] > 0: details.append(f"{s['todo']} todo")
            if s["in_progress"] > 0: details.append(f"{s['in_progress']} active")
            if s["review"] > 0: details.append(f"{s['review']} review")
            if details:
                lines.append(f"  _{', '.join(details)}_")

        # Overdue warning
        overdue = await task_service.get_overdue_tasks(db)
        if overdue:
            lines.append(f"\n\U0001F534 *{len(overdue)} overdue task(s):*")
            for t in overdue[:5]:
                lines.append(f"  \u2022 #{t.id} {t.title} \u2192 _{t.assignee_name}_")

        await telegram_service.send_message(chat_id, "\n".join(lines))

    # ─── TRACK COMMAND (create task from message reply) ───

    async def _cmd_track(self, db, chat_id, user_id, user_name, args, message):
        reply = message.get("reply_to_message")
        if not reply:
            await telegram_service.send_message(chat_id, "\u2757 Reply to a message with /track to create a task from it.")
            return

        reply_text = reply.get("text", "")
        if not reply_text:
            await telegram_service.send_message(chat_id, "The replied message has no text to track.")
            return

        task = await task_service.create_task_from_message(
            db, message_text=reply_text, creator_id=user_id, creator_name=user_name,
            chat_id=chat_id, message_id=reply["message_id"],
        )
        sender_name = reply.get("from", {}).get("first_name", "Unknown")
        await telegram_service.send_message(
            chat_id,
            f"\U0001F4CC Task *#{task.id}* created from {sender_name}'s message:\n*{task.title[:100]}*\nAssigned to: {user_name}"
        )

    # ─── REPORT COMMAND (AI-generated) ───

    async def _cmd_report(self, db, chat_id, user_id, user_name, args, message):
        report_type = args.strip().lower() if args else "daily"
        await telegram_service.send_message(chat_id, "\U0001F504 Generating report...")

        if report_type == "weekly":
            data = await task_service.get_weekly_report_data(db)
            completed = [{"title": t.title, "assignee": t.assignee_name or "?"} for t in data["completed_week"]]
            in_progress = [{"title": t.title, "assignee": t.assignee_name or "?"} for t in data["active_tasks"]]
            report = await ai_engine.generate_weekly_report(completed, in_progress, data["team_stats"])
            await telegram_service.send_message(chat_id, f"\U0001F4CA *Weekly Team Report*\n\n{report}")
        else:
            data = await task_service.get_daily_report_data(db)
            completed = [{"title": t.title, "assignee": t.assignee_name or "?"} for t in data["completed_today"]]
            events = []  # Calendar events would be added here
            report = await ai_engine.generate_daily_summary(
                [{"title": t.title, "status": t.status.value, "assignee": t.assignee_name or "?"} for t in data["active_tasks"]],
                events,
                0,
            )
            lines = [f"\U0001F4CA *Daily Report*\n\n{report}"]
            if data["overdue_tasks"]:
                lines.append(f"\n\U0001F534 *Overdue ({len(data['overdue_tasks'])}):*")
                for t in data["overdue_tasks"][:5]:
                    lines.append(f"  \u2022 #{t.id} {t.title} \u2192 _{t.assignee_name}_")
            await telegram_service.send_message(chat_id, "\n".join(lines))

    # ─── EXISTING COMMANDS ───

    async def _cmd_summary(self, db, chat_id, user_id, user_name, args, message):
        result = await db.execute(
            select(Message).where(Message.chat_id == chat_id, Message.is_command == False)
            .order_by(desc(Message.created_at)).limit(50)
        )
        messages = result.scalars().all()
        if not messages:
            await telegram_service.send_message(chat_id, "No messages to summarize yet.")
            return
        msg_dicts = [{"sender": m.sender_name, "text": m.text} for m in reversed(messages) if m.text]
        await telegram_service.send_message(chat_id, "\U0001F504 Generating summary...")
        summary = await ai_engine.summarize_messages(msg_dicts)
        await telegram_service.send_message(chat_id, f"\U0001F4CB *Message Summary*\n\n{summary}")

    async def _cmd_remind(self, db, chat_id, user_id, user_name, args, message):
        if not args:
            await telegram_service.send_message(chat_id, "Usage:\n`/remind <minutes> <message>`\n`/remind 2026-03-10T14:00 <message>`\n\nExample: `/remind 30 Check deployment status`")
            return
        # Try absolute datetime first: /remind 2026-03-10T14:00 message
        dt_match = re.match(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})\s+(.+)", args)
        if dt_match:
            try:
                remind_at = datetime.fromisoformat(dt_match.group(1)).replace(tzinfo=timezone.utc)
                reminder_text = dt_match.group(2)
                reminder = Reminder(user_id=user_id, chat_id=chat_id, message=reminder_text, remind_at=remind_at)
                db.add(reminder)
                await telegram_service.send_message(chat_id, f"\u23f0 Reminder set for *{remind_at.strftime('%b %d, %Y %H:%M')} UTC*:\n_{reminder_text}_")
                return
            except ValueError:
                pass
        # Fallback: relative minutes
        match = re.match(r"(\d+)\s+(.+)", args)
        if not match:
            await telegram_service.send_message(chat_id, "Usage: `/remind <minutes> <message>`\nExample: `/remind 30 Check deployment status`")
            return
        minutes = int(match.group(1))
        reminder_text = match.group(2)
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        reminder = Reminder(user_id=user_id, chat_id=chat_id, message=reminder_text, remind_at=remind_at)
        db.add(reminder)
        await telegram_service.send_message(chat_id, f"\u23f0 Reminder set for *{minutes} minutes* from now:\n_{reminder_text}_")


    async def _cmd_send(self, db, chat_id, user_id, user_name, args, message):
        if not is_admin(user_id):
            await telegram_service.send_message(chat_id, "\u26D4 Only the admin can use /send.")
            return
        match = re.match(r"(-?\d+)\s+(.+)", args)
        if not match:
            await telegram_service.send_message(chat_id, "Usage: `/send <chat_id> <message>`")
            return
        target_chat = int(match.group(1))
        msg_text = match.group(2)
        result = await telegram_service.send_message(target_chat, msg_text)
        if result.get("ok"):
            await telegram_service.send_message(chat_id, "\u2705 Message sent!")
        else:
            await telegram_service.send_message(chat_id, f"\u274C Failed: {result.get('description', 'Unknown error')}")

    # ─── PHASE 4: AI INTELLIGENCE COMMANDS ───

    async def _cmd_translate(self, db, chat_id, user_id, user_name, args, message):
        reply = message.get("reply_to_message")
        text_to_translate = args or (reply.get("text", "") if reply else "")
        if not text_to_translate:
            await telegram_service.send_message(chat_id, "\U0001F30F `/translate <text>` or reply to a message with /translate")
            return
        translation = await ai_engine.translate(text_to_translate)
        await telegram_service.send_message(chat_id, f"\U0001F30F *Translation:*\n\n{translation}")

    async def _cmd_extract(self, db, chat_id, user_id, user_name, args, message):
        reply = message.get("reply_to_message")
        text = args or (reply.get("text", "") if reply else "")
        if not text:
            await telegram_service.send_message(chat_id, "\U0001F9E0 Reply to a message with /extract or: `/extract <text>`")
            return
        await telegram_service.send_message(chat_id, "\U0001F504 Analyzing for tasks...")
        tasks = await ai_engine.extract_tasks(text)
        if not tasks:
            await telegram_service.send_message(chat_id, "No actionable tasks detected.")
            return
        lines = [f"\U0001F9E0 *Detected {len(tasks)} task(s):*\n"]
        for t in tasks:
            title = t.get("title", "Untitled")
            assignee = t.get("assignee", "unassigned")
            priority_str = t.get("priority", "medium")
            try:
                priority = TaskPriority(priority_str)
            except ValueError:
                priority = TaskPriority.MEDIUM
            task = await task_service.create_task(
                db, title=title, creator_id=user_id, creator_name=user_name,
                priority=priority, label=t.get("label"),
                assignee_name=assignee if assignee != "unassigned" else user_name,
                source_chat_id=chat_id,
            )
            prio_icon = PRIORITY_ICONS.get(priority.value, "")
            lines.append(f"  {prio_icon} *#{task.id}* {title} \u2192 _{task.assignee_name}_")
        lines.append(f"\n\u2705 All {len(tasks)} tasks created!")
        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def _cmd_insights(self, db, chat_id, user_id, user_name, args, message):
        tasks = await task_service.get_all_tasks(db, exclude_done=True, limit=30)
        overdue = await task_service.get_overdue_tasks(db)
        stats = await task_service.get_team_stats(db)
        context = f"User: {user_name}\nActive tasks ({len(tasks)}):\n"
        context += "\n".join([f"- [{t.status.value}] {t.title} -> {t.assignee_name} (priority: {t.priority.value})" + (f" DUE: {t.due_date}" if t.due_date else "") for t in tasks])
        if overdue:
            context += f"\n\nOverdue ({len(overdue)}):\n" + "\n".join([f"- OVERDUE: {t.title} -> {t.assignee_name}" for t in overdue])
        context += f"\n\nTeam stats: {stats}"
        insights = await ai_engine.get_proactive_insights(context)
        if insights:
            await telegram_service.send_message(chat_id, f"\U0001F4A1 *Work Insights:*\n\n{insights}")
        else:
            await telegram_service.send_message(chat_id, "\u2705 Everything looks good! No urgent insights.")

    async def _cmd_draft(self, db, chat_id, user_id, user_name, args, message):
        if not args:
            await telegram_service.send_message(chat_id, "\u270D\uFE0F `/draft <what you want to say>`\n\nExamples:\n\u2022 `/draft remind team about Friday deadline`\n\u2022 `/draft ask Dara for ETL update`")
            return
        await telegram_service.send_message(chat_id, "\u270D\uFE0F Drafting...")
        draft = await ai_engine.draft_message(args)
        await telegram_service.send_message(chat_id, f"\u270D\uFE0F *Draft:*\n\n{draft}")

    # ─── ENHANCED AI CHAT (Phase 4) ───

    async def _handle_ai_chat(self, db, chat_id, user_id, user_name, text):
        tasks = await task_service.get_tasks(db, user_id=user_id, limit=10)
        all_tasks = await task_service.get_all_tasks(db, exclude_done=True, limit=20)
        overdue = await task_service.get_overdue_tasks(db)
        task_context = "\n".join([f"- [{t.status.value}] #{t.id} {t.title} (assigned: {t.assignee_name}, priority: {t.priority.value})" for t in tasks]) if tasks else "No personal tasks"
        team_context = "\n".join([f"- [{t.status.value}] #{t.id} {t.title} -> {t.assignee_name}" for t in all_tasks]) if all_tasks else "No team tasks"
        overdue_context = "\n".join([f"- OVERDUE: #{t.id} {t.title} -> {t.assignee_name}" for t in overdue]) if overdue else ""
        context = f"User: {user_name}\n\nYour tasks:\n{task_context}\n\nAll team tasks:\n{team_context}"
        if overdue_context:
            context += f"\n\nOverdue:\n{overdue_context}"
        response, actions = await ai_engine.chat_with_actions(text, context)
        action_results = []
        for action in actions:
            result = await self._execute_action(db, action, user_id, user_name, chat_id)
            if result:
                action_results.append(result)
        await telegram_service.send_message(chat_id, response)
        for r in action_results:
            await telegram_service.send_message(chat_id, r)

    async def _handle_file_chat(self, db, chat_id, user_id, user_name, caption, file_id, file_name):
        """Handle file uploads in private chat — download, process, and analyze with AI."""
        await telegram_service.send_message(chat_id, f"\U0001F4C4 Processing *{file_name}*...")
        try:
            from app.services.file_processor import extract_text_from_file
            from app.core.config import get_settings
            import httpx

            settings = get_settings()
            bot_token = settings.telegram_bot_token

            # Get file path from Telegram
            async with httpx.AsyncClient() as client:
                file_info = await client.get(f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}")
                file_path = file_info.json().get("result", {}).get("file_path")
                if not file_path:
                    await telegram_service.send_message(chat_id, "\u274C Could not download the file.")
                    return

                # Download file
                file_resp = await client.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}")
                file_bytes = file_resp.content

            # Extract content
            file_data = await extract_text_from_file(file_bytes, file_name)

            # Build message
            user_msg = caption or f"Analyze this file: {file_name}"

            # Call AI with file
            response = await ai_engine.chat_with_file(user_msg, file_data)
            await telegram_service.send_message(chat_id, f"\U0001F4C4 *{file_data['summary']}*\n\n{response}")

        except Exception as e:
            logger.error(f"File processing error: {e}")
            await telegram_service.send_message(chat_id, f"\u274C Error processing file: {str(e)}")

    async def _execute_action(self, db, action, user_id, user_name, chat_id):
        try:
            a = action.get("action")
            if a == "create_task":
                try:
                    priority = TaskPriority(action.get("priority", "medium"))
                except ValueError:
                    priority = TaskPriority.MEDIUM
                task = await task_service.create_task(
                    db, title=action.get("title", "New task"), creator_id=user_id, creator_name=user_name,
                    priority=priority, label=action.get("label"), assignee_name=action.get("assignee") or user_name,
                    source_chat_id=chat_id,
                )
                return f"\u2705 Task *#{task.id}* created: *{task.title}*"
            elif a == "complete_task":
                task = await task_service.update_status(db, int(action.get("task_id", 0)), TaskStatus.DONE)
                return f"\u2705 Task completed!" if task else None
            elif a == "assign_task":
                task = await task_service.assign_task(db, int(action.get("task_id", 0)), 0, action.get("assignee", ""))
                return f"\U0001F464 Task assigned to *{action.get('assignee')}*" if task else None
            elif a == "set_reminder":
                minutes = int(action.get("minutes", 30))
                msg = action.get("message", "Reminder")
                reminder = Reminder(user_id=user_id, chat_id=chat_id, message=msg, remind_at=datetime.now(timezone.utc) + timedelta(minutes=minutes))
                db.add(reminder)
                return f"\u23F0 Reminder set: {minutes}min \u2014 _{msg}_"
        except Exception as e:
            logger.error(f"Action error: {e}")
        return None

    async def _cmd_calendar(self, db, chat_id, user_id, user_name, args, message):
        from app.bot.calendar_cmds import calendar_handlers
        text = message.get("text", "")
        command = text.strip().split()[0].lower().split("@")[0]
        cal_cmds = {
            "/connect": calendar_handlers.cmd_connect,
            "/today": calendar_handlers.cmd_today,
            "/week": calendar_handlers.cmd_week,
            "/free": calendar_handlers.cmd_free,
            "/event": calendar_handlers.cmd_event,
            "/cancel": calendar_handlers.cmd_cancel,
        }
        handler = cal_cmds.get(command)
        if handler:
            await handler(db, chat_id, user_id, user_name, args, message)


    async def _handle_callback_query(self, callback_query: dict, db: AsyncSession):
        """Handle inline keyboard button presses (snooze reminders)."""
        query_id = callback_query.get("id")
        data = callback_query.get("data", "")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        message_id = callback_query.get("message", {}).get("message_id")
        user_id = callback_query.get("from", {}).get("id")

        # Only admin can use snooze buttons
        if not is_admin(user_id):
            await telegram_service.answer_callback_query(query_id, "Not authorized")
            return

        # Parse snooze callback: snooze_{minutes}_{reminder_id}
        import re as _re
        match = _re.match(r"snooze_(\d+)_(\d+)", data)
        if not match:
            await telegram_service.answer_callback_query(query_id, "Unknown action")
            return

        minutes = int(match.group(1))
        reminder_id = int(match.group(2))

        try:
            result = await db.execute(select(Reminder).where(Reminder.id == reminder_id))
            reminder = result.scalar_one_or_none()
            if not reminder:
                await telegram_service.answer_callback_query(query_id, "Reminder not found")
                return

            # Store original time on first snooze
            if not reminder.original_remind_at:
                reminder.original_remind_at = reminder.remind_at

            # Snooze: reset for re-delivery
            new_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
            reminder.remind_at = new_time
            reminder.is_sent = False
            reminder.snooze_count = (reminder.snooze_count or 0) + 1
            await db.commit()

            # Determine label
            if minutes >= 1440:
                label = "tomorrow"
            elif minutes >= 60:
                label = f"{minutes // 60}h"
            else:
                label = f"{minutes}m"

            # Acknowledge and update the message
            await telegram_service.answer_callback_query(
                query_id, f"\u23f0 Snoozed for {label}! Will remind at {new_time.strftime('%H:%M UTC')}"
            )

            # Remove inline keyboard from the original message
            if chat_id and message_id:
                try:
                    await telegram_service.edit_message_reply_markup(chat_id, message_id)
                except Exception:
                    pass  # Message may be too old to edit

            logger.info(f"Snoozed reminder {reminder_id} for {minutes}m (count: {reminder.snooze_count})")
        except Exception as e:
            logger.error(f"Snooze callback error: {e}")
            await telegram_service.answer_callback_query(query_id, "Error processing snooze")


bot_handlers = BotHandlers()
