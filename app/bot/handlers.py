"""
Telegram Bot Command Handlers — processes incoming messages and commands.
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

# Task-related keywords for auto-detection
TASK_KEYWORDS = re.compile(r"\b(TODO|ACTION|DEADLINE|URGENT|ASAP|FOLLOW.?UP|ASSIGNED)\b", re.IGNORECASE)


class BotHandlers:
    """Processes Telegram updates and routes to appropriate handlers."""

    async def handle_update(self, update: dict, db: AsyncSession):
        """Main entry point for processing a Telegram update."""
        message = update.get("message")
        if not message:
            return

        chat_id = message["chat"]["id"]
        text = message.get("text", "")
        user = message.get("from", {})
        user_id = user.get("id")
        user_name = user.get("first_name", "Unknown")
        chat_title = message["chat"].get("title", "Private")

        # Store message in database
        await self._store_message(db, message)

        # Handle commands
        if text.startswith("/"):
            await self._handle_command(db, chat_id, user_id, user_name, text, message)
        else:
            # For non-command messages in private chats, treat as AI conversation
            if message["chat"]["type"] == "private":
                await self._handle_ai_chat(db, chat_id, user_id, user_name, text)

    async def _store_message(self, db: AsyncSession, message: dict):
        """Store a Telegram message in the database."""
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

    async def _handle_command(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, text: str, message: dict):
        """Route commands to their handlers."""
        parts = text.strip().split(maxsplit=1)
        command = parts[0].lower().split("@")[0]  # Remove @botname suffix
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/status": self._cmd_status,
            "/summary": self._cmd_summary,
            "/task": self._cmd_task,
            "/remind": self._cmd_remind,
            "/send": self._cmd_send,
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
            await telegram_service.send_message(
                chat_id, f"Unknown command: `{command}`\nType /help to see available commands."
            )

    # ─── Command Implementations ───

    async def _cmd_start(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Register user and show welcome message."""
        # Upsert user
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
            status = "registered"
        else:
            status = "already registered"

        await telegram_service.send_message(chat_id, f"""👋 *Welcome to AI Personal Assistant!*

You are {status} as *{user_name}*.

I can help you with:
• 📬 Summarize group messages
• ✅ Manage tasks and assignments
• ⏰ Set reminders
• 📅 Check your calendar _(coming soon)_
• 🤖 Chat with AI for anything else

Type /help to see all commands.""")

    async def _cmd_help(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        await telegram_service.send_message(chat_id, """📖 *Available Commands*

*General*
/start — Register and get started
/help — Show this help message
/status — Your stats and system status

*Messages*
/summary — Summarize recent messages in this group
/send <group\\_name> <message> — Send message on your behalf

*Tasks*
/task add <title> — Create a new task
/task list — Show your pending tasks
/task done <id> — Mark task as completed
/task assign <id> @user — Assign task to someone

*Reminders*
/remind <minutes> <message> — Set a reminder

*AI Chat*
Just send me any message in private chat and I'll help!""")

    async def _cmd_status(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Show user stats and system status."""
        # Count user's tasks
        tasks = await task_service.get_tasks(db, user_id=user_id, limit=100)
        todo = sum(1 for t in tasks if t.status == TaskStatus.TODO)
        in_prog = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)

        await telegram_service.send_message(chat_id, f"""📊 *Status for {user_name}*

*Your Tasks:*
• 📋 To Do: {todo}
• 🔄 In Progress: {in_prog}
• ✅ Completed: {done}

*System:* 🟢 Online
*AI Engine:* 🟢 Ready""")

    async def _cmd_summary(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Summarize recent messages in the current group."""
        result = await db.execute(
            select(Message)
            .where(Message.chat_id == chat_id, Message.is_command == False)
            .order_by(desc(Message.created_at))
            .limit(50)
        )
        messages = result.scalars().all()

        if not messages:
            await telegram_service.send_message(chat_id, "No messages to summarize yet. I'll start tracking from now!")
            return

        msg_dicts = [{"sender": m.sender_name, "text": m.text} for m in reversed(messages) if m.text]
        await telegram_service.send_message(chat_id, "🔄 Generating summary...")

        summary = await ai_engine.summarize_messages(msg_dicts)
        await telegram_service.send_message(chat_id, f"📋 *Message Summary*\n\n{summary}")

    async def _cmd_task(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Handle task subcommands: add, list, done, assign."""
        if not args:
            await telegram_service.send_message(chat_id, "Usage: `/task add <title>`, `/task list`, `/task done <id>`, `/task assign <id> @user`")
            return

        parts = args.split(maxsplit=1)
        subcmd = parts[0].lower()
        subargs = parts[1] if len(parts) > 1 else ""

        if subcmd == "add" and subargs:
            task = await task_service.create_task(
                db, title=subargs, creator_id=user_id, creator_name=user_name,
                source_chat_id=chat_id, source_message_id=message["message_id"],
            )
            await telegram_service.send_message(
                chat_id, f"✅ Task #{task.id} created: *{task.title}*\nAssigned to: {user_name}"
            )

        elif subcmd == "list":
            tasks = await task_service.get_tasks(db, user_id=user_id)
            if not tasks:
                await telegram_service.send_message(chat_id, "No pending tasks! 🎉")
                return
            status_icons = {"todo": "📋", "in_progress": "🔄", "review": "👀", "done": "✅"}
            lines = []
            for t in tasks:
                icon = status_icons.get(t.status.value, "•")
                lines.append(f"{icon} #{t.id} {t.title}")
            await telegram_service.send_message(chat_id, f"*Your Tasks:*\n\n" + "\n".join(lines))

        elif subcmd == "done" and subargs:
            try:
                task_id = int(subargs.strip())
                task = await task_service.update_status(db, task_id, TaskStatus.DONE)
                if task:
                    await telegram_service.send_message(chat_id, f"✅ Task #{task_id} completed: *{task.title}*")
                else:
                    await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
            except ValueError:
                await telegram_service.send_message(chat_id, "Usage: `/task done <id>`")

        elif subcmd == "assign" and subargs:
            # Parse: <task_id> @username or name
            match = re.match(r"(\d+)\s+@?(\S+)", subargs)
            if match:
                task_id = int(match.group(1))
                assignee = match.group(2)
                task = await task_service.assign_task(db, task_id, 0, assignee)
                if task:
                    await telegram_service.send_message(chat_id, f"👤 Task #{task_id} assigned to *{assignee}*")
                else:
                    await telegram_service.send_message(chat_id, f"Task #{task_id} not found.")
            else:
                await telegram_service.send_message(chat_id, "Usage: `/task assign <id> @username`")
        else:
            await telegram_service.send_message(chat_id, "Unknown task command. Try: `add`, `list`, `done`, `assign`")

    async def _cmd_remind(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Set a reminder: /remind <minutes> <message>."""
        match = re.match(r"(\d+)\s+(.+)", args)
        if not match:
            await telegram_service.send_message(chat_id, "Usage: `/remind <minutes> <message>`\nExample: `/remind 30 Check deployment status`")
            return

        minutes = int(match.group(1))
        reminder_text = match.group(2)
        remind_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)

        reminder = Reminder(
            user_id=user_id,
            chat_id=chat_id,
            message=reminder_text,
            remind_at=remind_at,
        )
        db.add(reminder)

        await telegram_service.send_message(
            chat_id, f"⏰ Reminder set for *{minutes} minutes* from now:\n_{reminder_text}_"
        )

    async def _cmd_send(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Send a message to a group on the user's behalf (admin only)."""
        if not is_admin(user_id):
            await telegram_service.send_message(chat_id, "⛔ Only the admin can use /send.")
            return

        match = re.match(r"(-?\d+)\s+(.+)", args)
        if not match:
            await telegram_service.send_message(chat_id, "Usage: `/send <chat_id> <message>`")
            return

        target_chat = int(match.group(1))
        msg_text = match.group(2)
        result = await telegram_service.send_message(target_chat, msg_text)
        if result.get("ok"):
            await telegram_service.send_message(chat_id, "✅ Message sent!")
        else:
            await telegram_service.send_message(chat_id, f"❌ Failed: {result.get('description', 'Unknown error')}")

    async def _handle_ai_chat(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, text: str):
        """Handle free-form AI conversation in private chat."""
        # Build context
        tasks = await task_service.get_tasks(db, user_id=user_id, limit=10)
        task_context = "\n".join([f"- [{t.status.value}] {t.title}" for t in tasks]) if tasks else "No tasks"

        context = f"""User: {user_name}
Pending tasks:
{task_context}"""

        response = await ai_engine.chat(text, context=context)
        await telegram_service.send_message(chat_id, response)

    async def _cmd_calendar(self, db: AsyncSession, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Route calendar commands to CalendarHandlers."""
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


# Singleton
bot_handlers = BotHandlers()
