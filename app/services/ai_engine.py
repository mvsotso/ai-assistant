"""
AI Engine — Claude integration for intelligent assistant capabilities.
Handles intent classification, message summarization, task extraction, and conversational AI.
"""
import anthropic
from app.core.config import get_settings

settings = get_settings()

SYSTEM_PROMPT = """You are a personal AI assistant for Sot So, Chief of Data Management Bureau at the General Department of Taxation (GDT) in Cambodia. You help manage:

1. **Telegram Messages** — Summarize group conversations, track action items, send messages
2. **Google Calendar** — Check schedule, find free slots, set reminders, create events
3. **Team Tasks** — Create, assign, track, and report on tasks across the team

Team members: Sot So (admin), Dara, Sophea, Visal, Bopha, Kosal

You respond concisely and professionally. Use bullet points for lists. Include relevant emojis for readability. When extracting tasks, identify: title, assignee (if mentioned), priority, and due date.

Current timezone: Asia/Phnom_Penh (UTC+7)

When asked to perform actions (send message, create task, set reminder), respond with a structured JSON action block that the system can execute, wrapped in ```action tags.
"""


class AIEngine:
    """Claude-powered AI assistant engine."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

    async def chat(self, user_message: str, context: str = "") -> str:
        """Process a user message and return AI response."""
        system = SYSTEM_PROMPT
        if context:
            system += f"\n\nCurrent context:\n{context}"

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except Exception as e:
            return f"Sorry, I encountered an error: {str(e)}"

    async def summarize_messages(self, messages: list[dict]) -> str:
        """Summarize a list of Telegram messages."""
        msg_text = "\n".join(
            [f"[{m['sender']}] {m['text']}" for m in messages if m.get("text")]
        )
        prompt = f"""Summarize the following group chat messages concisely. 
Group by topic/thread. Highlight action items, decisions, and questions that need answers.

Messages:
{msg_text}"""

        return await self.chat(prompt)

    async def extract_tasks(self, text: str) -> str:
        """Extract actionable tasks from a message or conversation."""
        prompt = f"""Analyze this text and extract any actionable tasks. For each task, identify:
- Title (brief, action-oriented)
- Assignee (if mentioned, otherwise "unassigned")
- Priority (low/medium/high based on urgency words)
- Due date (if mentioned, otherwise null)

Respond in JSON format: {{"tasks": [{{"title": "...", "assignee": "...", "priority": "...", "due": "..."}}]}}

Text: {text}"""

        return await self.chat(prompt)

    async def generate_daily_summary(self, tasks: list, events: list, messages_count: int) -> str:
        """Generate a morning briefing summary."""
        task_text = "\n".join([f"- [{t['status']}] {t['title']} (assigned: {t['assignee']})" for t in tasks])
        event_text = "\n".join([f"- {e['time']}: {e['title']} ({e['duration']})" for e in events])

        prompt = f"""Generate a concise morning briefing for today.

Today's Events:
{event_text or "No events scheduled."}

Pending Tasks:
{task_text or "No pending tasks."}

Unread Messages: {messages_count}

Format it as a friendly, professional morning message with emojis. Keep it under 200 words."""

        return await self.chat(prompt)

    async def generate_weekly_report(self, completed: list, in_progress: list, team_stats: dict) -> str:
        """Generate a weekly team productivity report."""
        prompt = f"""Generate a weekly team summary report.

Completed this week ({len(completed)} tasks):
{chr(10).join([f"- {t['title']} by {t['assignee']}" for t in completed]) or "None"}

Still in progress ({len(in_progress)} tasks):
{chr(10).join([f"- {t['title']} by {t['assignee']}" for t in in_progress]) or "None"}

Team stats: {team_stats}

Format as a professional weekly report with sections: Highlights, In Progress, Blockers (if any), and Team Performance. Use emojis and keep it concise."""

        return await self.chat(prompt)


# Singleton instance
ai_engine = AIEngine()
