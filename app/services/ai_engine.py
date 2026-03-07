"""
AI Engine — Phase 4: Intelligent assistant with intent classification,
task extraction, proactive insights, Khmer language support, and action execution.
"""
import json
import logging
import anthropic
from datetime import datetime, timezone
from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a personal AI assistant for Sot So, Chief of Data Management Bureau at the General Department of Taxation (GDT) in Cambodia. You help manage:

1. **Telegram Messages** — Summarize group conversations, track action items
2. **Google Calendar** — Check schedule, find free slots, set reminders, create events
3. **Team Tasks** — Create, assign, track, and report on tasks

**Team members:** Sot So (admin), Dara, Sophea, Visal, Bopha, Kosal

**Communication Rules:**
- If the user writes in Khmer (ខ្មែរ), respond in Khmer
- If the user writes in English, respond in English
- If mixed, respond in the dominant language
- Always be concise and professional
- Use bullet points and emojis for readability

**Action System:**
When the user asks you to DO something (create task, set reminder, create event), you MUST include an action block in your response. Format:

```action
{"action": "create_task", "title": "...", "assignee": "...", "priority": "medium", "label": "...", "due": "..."}
```

Available actions:
- create_task: {title, assignee (optional), priority (low/medium/high/urgent), label (optional), due (optional ISO date)}
- create_event: {title, start, end, location (optional), description (optional), timezone}
- assign_task: {task_id, assignee}
- complete_task: {task_id}
- set_reminder: {minutes, message}

CRITICAL RULES FOR create_event:
- ALWAYS extract the EXACT date and time mentioned in the message. NEVER use today or current time.
- Dates must be ISO format with Cambodia timezone. Example: 2026-03-09T14:30:00+07:00
- If message says Monday 9 March 2026 at 2:30 PM, start MUST be 2026-03-09T14:30:00+07:00
- Set end to 1 hour after start if not specified.
- Extract event title from context (meeting name, demo name, etc.)
- Include ALL details in description: meeting links, passcodes, attendees.
- Always set timezone to Asia/Phnom_Penh

Only include action blocks when the user explicitly asks to create/do something. For questions and information, just respond normally.

**Proactive Insights:**
When you see the user's context (tasks, calendar, overdue items), proactively mention:
- Overdue tasks that need attention
- High-priority items coming up
- Suggestions for task delegation if someone is overloaded
- Scheduling conflicts or free time recommendations

Current timezone: Asia/Phnom_Penh (UTC+7)
Current date/time: {current_time}
"""

INTENT_PROMPT = """Classify the intent of this message into ONE of these categories:
- task_create: User wants to create a new task
- task_query: User asks about tasks, progress, status
- calendar_query: User asks about schedule, events, free time
- message_summary: User wants message/chat summary
- reminder_set: User wants to set a reminder
- general_chat: General question, advice, or conversation
- translation: User wants something translated
- report: User wants a report generated

Respond with ONLY the intent category, nothing else.

Message: {message}"""

TASK_EXTRACT_PROMPT = """Analyze this text and extract ALL actionable tasks. For each task provide:
- title: Brief, action-oriented title (max 100 chars)
- assignee: Person name if mentioned, otherwise "unassigned"
- priority: "low", "medium", "high", or "urgent" based on urgency signals
- due: ISO date string if a deadline is mentioned, otherwise null
- label: Category if obvious (e.g., "ETL", "GDT", "Kado24"), otherwise null

IMPORTANT: Respond ONLY with valid JSON, no markdown, no backticks:
{{"tasks": [{{"title": "...", "assignee": "...", "priority": "...", "due": null, "label": null}}]}}

Text to analyze:
{text}"""

SMART_SUMMARY_PROMPT = """Summarize the following group chat messages. Structure your summary as:

1. **Key Decisions** — Any decisions made
2. **Action Items** — Tasks or follow-ups mentioned (with who is responsible)
3. **Questions** — Unanswered questions that need attention
4. **Updates** — General status updates and information shared

For each action item, suggest it as a potential task to create.

If messages are in Khmer, summarize in Khmer. If English, summarize in English.

Messages:
{messages}"""

PROACTIVE_PROMPT = """Based on the user's current context, provide brief proactive insights:

Context:
{context}

Rules:
- If there are overdue tasks, mention them with urgency
- If a team member has too many tasks, suggest redistribution  
- If today's calendar is packed, suggest what to prioritize
- If there are tasks with no due date, suggest setting deadlines
- Keep it to 2-3 actionable bullet points max
- Be specific, not generic

Respond with just the insight bullets, or "No insights" if nothing stands out."""


class AIEngine:
    """Claude-powered AI assistant engine — Phase 4."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

    def _get_system_prompt(self) -> str:
        """Get system prompt with current timestamp."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return SYSTEM_PROMPT.replace("{current_time}", now)

    async def _call_claude(self, system: str, user_message: str, max_tokens: int = None) -> str:
        """Core Claude API call with error handling."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except anthropic.BadRequestError as e:
            logger.error(f"Claude API bad request: {e}")
            return f"Sorry, I couldn't process that request. Please try rephrasing."
        except anthropic.AuthenticationError:
            return "API authentication error. Please check the Anthropic API key."
        except anthropic.RateLimitError:
            return "I'm receiving too many requests right now. Please try again in a moment."
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return f"Sorry, I encountered an error: {str(e)}"

    async def _call_claude_multimodal(self, system: str, text: str, file_data: dict = None, max_tokens: int = None) -> str:
        """Claude API call with optional image/file support."""
        try:
            content = []
            # Add image if present
            if file_data and file_data.get("type") == "image":
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": file_data.get("media_type", "image/png"),
                        "data": file_data["content"],
                    },
                })
            # Add text with optional file content
            if file_data and file_data.get("type") == "text":
                text = f"{text}\n\n--- File: {file_data['filename']} ---\n{file_data['content']}"
            content.append({"type": "text", "text": text})

            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": content}],
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Claude multimodal error: {e}")
            return f"Sorry, I couldn't process that file: {str(e)}"

    async def chat_with_file(self, user_message: str, file_data: dict = None, context: str = "") -> str:
        """Process a message with optional file attachment."""
        system = self._get_system_prompt()
        if context:
            system += f"\n\nCurrent context:\n{context}"
        if file_data:
            return await self._call_claude_multimodal(system, user_message, file_data)
        return await self._call_claude(system, user_message)

    # ─── INTENT CLASSIFICATION ───

    async def classify_intent(self, message: str) -> str:
        """Classify user message intent using a fast call."""
        result = await self._call_claude(
            "You are an intent classifier. Respond with ONLY the intent category.",
            INTENT_PROMPT.replace("{message}", message),
            max_tokens=50,
        )
        intent = result.strip().lower().replace(" ", "_")
        valid_intents = ["task_create", "task_query", "calendar_query", "message_summary", "reminder_set", "general_chat", "translation", "report"]
        return intent if intent in valid_intents else "general_chat"

    # ─── MAIN CHAT ───

    async def chat(self, user_message: str, context: str = "") -> str:
        """Process a user message with full context and return AI response."""
        system = self._get_system_prompt()
        if context:
            system += f"\n\nCurrent context:\n{context}"
        return await self._call_claude(system, user_message)

    async def chat_with_actions(self, user_message: str, context: str = "") -> tuple[str, list[dict]]:
        """Chat and extract any action blocks from the response."""
        response = await self.chat(user_message, context)

        # Extract action blocks
        actions = []
        if "```action" in response:
            parts = response.split("```action")
            for part in parts[1:]:
                json_end = part.find("```")
                if json_end > 0:
                    json_str = part[:json_end].strip()
                    try:
                        action = json.loads(json_str)
                        actions.append(action)
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse action JSON: {json_str}")

            # Clean action blocks from display text
            clean_response = response.split("```action")[0].strip()
            for part in response.split("```"):
                if not part.startswith("action") and part.strip():
                    # Keep non-action text after blocks
                    pass
            if clean_response:
                response = clean_response

        return response, actions

    # ─── TASK EXTRACTION ───

    async def extract_tasks(self, text: str) -> list[dict]:
        """Extract actionable tasks from text. Returns list of task dicts."""
        result = await self._call_claude(
            "You extract tasks from text. Respond ONLY with valid JSON.",
            TASK_EXTRACT_PROMPT.replace("{text}", text),
            max_tokens=1000,
        )

        # Parse JSON from response
        try:
            # Clean potential markdown formatting
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            parsed = json.loads(clean)
            return parsed.get("tasks", [])
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse task extraction: {result}")
            return []

    async def extract_tasks_from_messages(self, messages: list[dict]) -> list[dict]:
        """Extract tasks from a batch of chat messages."""
        msg_text = "\n".join([f"[{m.get('sender', '?')}] {m.get('text', '')}" for m in messages if m.get('text')])
        if not msg_text:
            return []
        return await self.extract_tasks(msg_text)

    # ─── SMART SUMMARIZATION ───

    async def summarize_messages(self, messages: list[dict]) -> str:
        """Summarize messages with structured output and task detection."""
        msg_text = "\n".join([f"[{m.get('sender', '?')}] {m.get('text', '')}" for m in messages if m.get("text")])
        if not msg_text:
            return "No messages to summarize."
        return await self._call_claude(
            self._get_system_prompt(),
            SMART_SUMMARY_PROMPT.replace("{messages}", msg_text),
        )

    # ─── PROACTIVE INSIGHTS ───

    async def get_proactive_insights(self, context: str) -> str:
        """Generate proactive insights based on current user context."""
        result = await self._call_claude(
            "You provide brief, actionable work insights. Be specific and concise.",
            PROACTIVE_PROMPT.replace("{context}", context),
            max_tokens=500,
        )
        if "no insights" in result.lower() or not result.strip():
            return ""
        return result.strip()

    # ─── REPORTS ───

    async def generate_daily_summary(self, tasks: list, events: list, messages_count: int) -> str:
        task_text = "\n".join([f"- [{t['status']}] {t['title']} (assigned: {t['assignee']})" for t in tasks])
        event_text = "\n".join([f"- {e['time']}: {e['title']} ({e['duration']})" for e in events])

        prompt = f"""Generate a concise morning briefing for today.

Today's Events:
{event_text or "No events scheduled."}

Pending Tasks:
{task_text or "No pending tasks."}

Unread Messages: {messages_count}

Format as a friendly, professional morning message with emojis.
If the user typically communicates in Khmer, include a Khmer greeting.
Keep it under 200 words."""

        return await self._call_claude(self._get_system_prompt(), prompt)

    async def generate_weekly_report(self, completed: list, in_progress: list, team_stats: dict) -> str:
        prompt = f"""Generate a weekly team summary report.

Completed this week ({len(completed)} tasks):
{chr(10).join([f"- {t['title']} by {t['assignee']}" for t in completed]) or "None"}

Still in progress ({len(in_progress)} tasks):
{chr(10).join([f"- {t['title']} by {t['assignee']}" for t in in_progress]) or "None"}

Team stats: {team_stats}

Format as a professional weekly report with sections:
1. Highlights & Achievements
2. In Progress
3. Blockers & Risks
4. Team Performance Summary
5. Recommendations for Next Week

Use emojis and keep it concise but comprehensive."""

        return await self._call_claude(self._get_system_prompt(), prompt)

    # ─── TRANSLATION ───

    async def translate(self, text: str, target_lang: str = "auto") -> str:
        """Translate text between English and Khmer."""
        prompt = f"""Translate the following text.
If the text is in English, translate to Khmer (ខ្មែរ).
If the text is in Khmer, translate to English.
If target language is specified as "{target_lang}", translate to that language.

Provide ONLY the translation, nothing else.

Text: {text}"""

        return await self._call_claude(
            "You are a professional English-Khmer translator. Respond with ONLY the translation.",
            prompt,
        )

    # ─── SMART TASK CREATION FROM NATURAL LANGUAGE ───

    async def parse_task_request(self, message: str) -> dict | None:
        """Parse a natural language task creation request into structured data."""
        prompt = f"""Parse this task creation request into structured data.

Request: {message}

Team members: Sot So, Dara, Sophea, Visal, Bopha, Kosal

Respond ONLY with valid JSON (no markdown):
{{
    "title": "brief task title",
    "assignee": "name or null",
    "priority": "low|medium|high|urgent",
    "label": "category or null",
    "due_description": "human readable due date or null",
    "understood": true
}}

If you cannot understand the request, set "understood" to false."""

        result = await self._call_claude(
            "You parse task requests into JSON. Respond with ONLY valid JSON.",
            prompt,
            max_tokens=300,
        )

        try:
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                clean = clean.rsplit("```", 1)[0]
            parsed = json.loads(clean)
            if parsed.get("understood", False):
                return parsed
            return None
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse task request: {result}")
            return None

    # ─── MESSAGE DRAFTING ───

    async def draft_message(self, request: str, context: str = "") -> str:
        """Draft a professional message based on user request."""
        prompt = f"""Draft a professional message based on this request:

Request: {request}

Context: {context}

Write the message ready to send. If the request is in Khmer, draft in Khmer.
Format it cleanly for Telegram (use Markdown sparingly)."""

        return await self._call_claude(self._get_system_prompt(), prompt)


# Singleton
ai_engine = AIEngine()
