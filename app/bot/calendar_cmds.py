"""
Calendar Bot Handlers — Telegram commands for Google Calendar integration.
Import and register these in the main BotHandlers class.
"""
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.calendar_svc import calendar_service, token_store
from app.services.telegram import telegram_service
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


class CalendarHandlers:
    """Telegram command handlers for Google Calendar features."""

    async def cmd_connect(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Connect Google Calendar via OAuth2."""
        auth_url = calendar_service.get_auth_url(state=str(user_id))
        await telegram_service.send_message(
            chat_id,
            f"🔗 *Connect Google Calendar*\n\n"
            f"Click the link below to authorize access to your calendar:\n\n"
            f"[Authorize Google Calendar]({auth_url})\n\n"
            f"_After authorizing, you'll be redirected back and your calendar will be connected._"
        )

    async def cmd_today(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Show today's calendar events."""
        creds = await token_store.load_token(db, user_id)
        if not creds:
            await telegram_service.send_message(
                chat_id, "⚠️ Google Calendar not connected. Use /connect to set it up."
            )
            return

        events = await calendar_service.get_today_events(creds)
        if not events:
            await telegram_service.send_message(chat_id, "📅 No events scheduled for today! Enjoy your free day.")
            return

        now = datetime.now(timezone.utc)
        day_str = now.strftime("%A, %B %d")
        lines = [f"📅 *Today's Schedule — {day_str}*\n"]
        for e in events:
            lines.append(f"• *{e['start']}* — {e['title']} ({e['duration']})")
            if e.get("location"):
                lines.append(f"  📍 {e['location']}")

        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def cmd_week(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Show upcoming 7 days of events."""
        creds = await token_store.load_token(db, user_id)
        if not creds:
            await telegram_service.send_message(
                chat_id, "⚠️ Google Calendar not connected. Use /connect to set it up."
            )
            return

        events = await calendar_service.get_week_events(creds)
        if not events:
            await telegram_service.send_message(chat_id, "📅 No events in the next 7 days!")
            return

        # Group events by date
        days = {}
        for e in events:
            try:
                dt = datetime.fromisoformat(e["start_raw"])
                day_key = dt.strftime("%A, %b %d")
            except (ValueError, TypeError):
                day_key = "Other"
            if day_key not in days:
                days[day_key] = []
            days[day_key].append(e)

        lines = ["📅 *Upcoming 7 Days*\n"]
        for day, evts in days.items():
            lines.append(f"\n*{day}*")
            for e in evts:
                lines.append(f"  • {e['start']} — {e['title']} ({e['duration']})")

        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def cmd_free(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Find free time slots today."""
        creds = await token_store.load_token(db, user_id)
        if not creds:
            await telegram_service.send_message(
                chat_id, "⚠️ Google Calendar not connected. Use /connect to set it up."
            )
            return

        slots = await calendar_service.find_free_slots(creds)
        if not slots:
            await telegram_service.send_message(chat_id, "😰 No free slots found today during working hours (8 AM – 6 PM).")
            return

        lines = ["🕐 *Available Time Slots Today*\n"]
        total_free = 0
        for s in slots:
            hrs = s["duration_minutes"] // 60
            mins = s["duration_minutes"] % 60
            dur_str = f"{hrs}h {mins}m" if hrs else f"{mins}m"
            lines.append(f"• *{s['start']}* → *{s['end']}* ({dur_str})")
            total_free += s["duration_minutes"]

        total_hrs = total_free // 60
        total_mins = total_free % 60
        lines.append(f"\n📊 Total free time: *{total_hrs}h {total_mins}m*")
        lines.append("\n_Reply with /event to create an event in a free slot._")

        await telegram_service.send_message(chat_id, "\n".join(lines))

    async def cmd_event(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """
        Create a calendar event.
        Usage: /event <title> at <time> for <duration>
        Example: /event Team sync at 2:00 PM for 30m
        """
        creds = await token_store.load_token(db, user_id)
        if not creds:
            await telegram_service.send_message(
                chat_id, "⚠️ Google Calendar not connected. Use /connect to set it up."
            )
            return

        if not args:
            await telegram_service.send_message(
                chat_id,
                "📅 *Create Event*\n\n"
                "Usage: `/event <title> at <time> for <duration>`\n\n"
                "Examples:\n"
                "• `/event Team sync at 2:00 PM for 30m`\n"
                "• `/event Code review at 10:00 AM for 1h`\n"
                "• `/event Lunch at 12:00 PM for 1h`"
            )
            return

        # Parse with AI if complex, or simple regex for basic format
        import re
        match = re.match(r"(.+?)\s+at\s+(\d{1,2}:\d{2}\s*[APap][Mm])\s+for\s+(\d+)\s*([hHmM])", args)
        if not match:
            # Fall back to AI parsing
            from app.services.ai_engine import ai_engine
            ai_response = await ai_engine.chat(
                f"Parse this event request and respond ONLY with JSON: {{\"title\": \"...\", \"hour\": 14, \"minute\": 0, \"duration_minutes\": 60}}\n\nRequest: {args}"
            )
            try:
                import json
                parsed = json.loads(ai_response.strip().strip("`").replace("json", ""))
                now = datetime.now(timezone.utc).replace(
                    hour=parsed["hour"], minute=parsed["minute"], second=0, microsecond=0
                )
                title = parsed["title"]
                duration = parsed["duration_minutes"]
            except Exception:
                await telegram_service.send_message(
                    chat_id, "❌ Could not parse event details. Try: `/event Meeting at 2:00 PM for 1h`"
                )
                return
        else:
            title = match.group(1).strip()
            time_str = match.group(2).strip()
            dur_val = int(match.group(3))
            dur_unit = match.group(4).lower()
            duration = dur_val * 60 if dur_unit == "h" else dur_val

            # Parse time
            try:
                event_time = datetime.strptime(time_str, "%I:%M %p")
                now = datetime.now(timezone.utc)
                start_time = now.replace(
                    hour=event_time.hour, minute=event_time.minute, second=0, microsecond=0
                )
            except ValueError:
                await telegram_service.send_message(chat_id, "❌ Invalid time format. Use: `2:00 PM`")
                return

        # Check conflicts
        end_time = start_time + timedelta(minutes=duration)
        conflicts = await calendar_service.check_conflicts(creds, start_time, end_time)
        if conflicts:
            conflict_names = ", ".join([c["title"] for c in conflicts])
            await telegram_service.send_message(
                chat_id,
                f"⚠️ *Conflict detected!*\nOverlaps with: {conflict_names}\n\nCreate anyway? (Feature coming soon — event created regardless for now)"
            )

        # Create event
        event = await calendar_service.create_event(
            creds, title=title, start_time=start_time, duration_minutes=duration
        )
        await telegram_service.send_message(
            chat_id,
            f"✅ *Event Created!*\n\n"
            f"📌 {event['title']}\n"
            f"🕐 {event['start']} → {event['end']} ({event['duration']})\n"
            f"🔗 [Open in Calendar]({event.get('link', '#')})"
        )

    async def cmd_cancel(self, db, chat_id: int, user_id: int, user_name: str, args: str, message: dict):
        """Cancel a calendar event by searching for it."""
        creds = await token_store.load_token(db, user_id)
        if not creds:
            await telegram_service.send_message(chat_id, "⚠️ Google Calendar not connected. Use /connect to set it up.")
            return

        if not args:
            await telegram_service.send_message(chat_id, "Usage: `/cancel <event name>`")
            return

        # Search today's events for a match
        events = await calendar_service.get_today_events(creds)
        search = args.lower()
        matches = [e for e in events if search in e["title"].lower()]

        if not matches:
            await telegram_service.send_message(chat_id, f"❌ No event matching \"{args}\" found today.")
            return

        event = matches[0]
        deleted = await calendar_service.delete_event(creds, event["id"])
        if deleted:
            await telegram_service.send_message(chat_id, f"🗑 *Cancelled:* {event['title']} at {event['start']}")
        else:
            await telegram_service.send_message(chat_id, "❌ Failed to cancel the event. Please try again.")


# Singleton
calendar_handlers = CalendarHandlers()
