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

**Document Generation (Word & PowerPoint):**
You CAN generate Word (.docx) and PowerPoint (.pptx) files! The system automatically converts your response into downloadable documents.

CRITICAL RULES for document generation:
- Do NOT use ```action blocks for document generation — NO action block needed!
- Do NOT say "I cannot create files" — you absolutely CAN
- Simply write the full document content directly in your response using markdown
- Use ## headings to create sections (these become separate slides in PowerPoint)
- Use bullet points, numbered lists, bold text, and tables
- Write comprehensive, well-structured content — the more detail, the better the document
- The download buttons (Word & PowerPoint) appear AUTOMATICALLY on your response
- When user says "create word document" or "create presentation" or "export to word", just write the content directly
- Start your response with the document content immediately — no preamble like "Here's your document" needed
- Example: If asked "create a summary report", write the full report with ## sections, lists, tables etc.

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

    async def _call_claude_history(self, system: str, messages: list, max_tokens: int = None) -> str:
        """Claude API call with full conversation history."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or self.max_tokens,
                system=system,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.BadRequestError as e:
            logger.error(f"Claude API bad request: {e}")
            return "Sorry, I couldn't process that request. Please try rephrasing."
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

    async def chat(self, user_message: str, context: str = "", history: list = None) -> str:
        """Process a user message with full context and conversation history."""
        system = self._get_system_prompt()
        if context:
            system += f"\n\nCurrent context:\n{context}"
        if history and len(history) > 0:
            # Build multi-turn messages: history + current message
            messages = []
            for msg in history[-20:]:  # Last 20 messages max
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
            # Add current message
            messages.append({"role": "user", "content": user_message})
            return await self._call_claude_history(system, messages)
        return await self._call_claude(system, user_message)

    async def chat_with_actions(self, user_message: str, context: str = "", history: list = None) -> tuple[str, list[dict]]:
        """Chat and extract any action blocks from the response."""
        response = await self.chat(user_message, context, history=history)

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


    # ─── TASK SUGGESTIONS ───

    async def suggest_tasks(self, existing_tasks: list, team_roles: list = None, recent_completed: list = None) -> list:
        """Suggest new tasks based on current task patterns and team workload."""
        tasks_str = "\n".join([f"- {t.get('title','')} ({t.get('status','')}, assigned to {t.get('assignee','Unassigned')}, priority: {t.get('priority','')})" for t in existing_tasks[:30]])
        completed_str = ""
        if recent_completed:
            completed_str = "\nRecently completed:\n" + "\n".join([f"- {t.get('title','')}" for t in recent_completed[:10]])
        team_str = ""
        if team_roles:
            team_str = "\nTeam: " + ", ".join([r.get('name', '') for r in team_roles[:10]])

        prompt = f"""Analyze these current tasks and suggest 3-5 NEW tasks that should be created:

Current tasks:
{tasks_str}
{completed_str}
{team_str}

Consider:
- Follow-up tasks from completed work
- Missing tasks implied by current work
- Gaps in coverage or delegation
- Upcoming deadlines that need preparation

Return ONLY a JSON array (no markdown, no explanation) like:
[{{"title": "...", "priority": "medium", "suggested_assignee": "...", "rationale": "Short reason"}}]"""

        result = await self._call_claude(self._get_system_prompt(), prompt)
        try:
            import json
            # Try to extract JSON from the response
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(clean)
        except (json.JSONDecodeError, IndexError):
            return []

    # ─── SMART REMINDER TIMING ───

    async def suggest_reminder_time(self, task_title: str, task_due_date: str = None, context: str = "") -> dict:
        """Suggest optimal reminder time based on task urgency and deadline."""
        prompt = f"""Given this task, suggest the optimal reminder time:

Task: {task_title}
Due date: {task_due_date or 'Not set'}
Current time: {datetime.now(timezone.utc).isoformat()}
Additional context: {context}

Consider:
- If due today, remind in 1 hour
- If due tomorrow, remind today evening or tomorrow morning
- If due in 2-3 days, remind 1 day before
- If due in a week+, remind 2-3 days before
- If no due date, suggest tomorrow morning (9:00 AM)

Return ONLY a JSON object (no markdown): {{"remind_at": "ISO datetime", "reason": "Short explanation"}}"""

        result = await self._call_claude(self._get_system_prompt(), prompt)
        try:
            import json
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json.loads(clean)
        except (json.JSONDecodeError, IndexError):
            # Fallback: suggest tomorrow 9 AM
            from datetime import timedelta
            tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
            tomorrow = tomorrow.replace(hour=2, minute=0, second=0, microsecond=0)  # 9 AM ICT = 2 AM UTC
            return {"remind_at": tomorrow.isoformat(), "reason": "Default: tomorrow morning"}

    async def prioritize_tasks(self, tasks: list, workload: dict) -> dict:
        """AI-powered task prioritization and workload analysis."""
        import json as json_mod
        tasks_str = json_mod.dumps(tasks, indent=2, default=str)[:8000]
        workload_str = json_mod.dumps(workload, indent=2) if workload else "No workload data"
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        prompt = f"""Analyze these tasks and provide prioritization with workload balancing.

Tasks:
{tasks_str}

Team workload:
{workload_str}

Current date: {now}

Consider: urgency (due dates), priority levels, blocked status, workload distribution.

Return ONLY valid JSON (no markdown):
{{
    "prioritized_tasks": [
        {{"id": 1, "score": 9, "reason": "brief reason", "suggested_priority": "high"}}
    ],
    "workload_recommendations": [
        {{"member": "Name", "current_load": 5, "recommendation": "brief recommendation"}}
    ],
    "summary": "Brief overall assessment"
}}"""

        result = await self._call_claude(
            "You are a project management AI. Analyze tasks and provide prioritization. Respond ONLY with valid JSON.",
            prompt,
            max_tokens=3000,
        )
        try:
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return json_mod.loads(clean)
        except (json_mod.JSONDecodeError, IndexError):
            return {"prioritized_tasks": [], "workload_recommendations": [], "summary": result}


# Singleton

    async def suggest_assignee(self, task_title: str, task_category: str = None,
                                task_priority: str = "medium", team_workload: dict = None) -> str:
        """Use AI to suggest the best assignee for a task."""
        workload_str = ", ".join(f"{name}: {count} active tasks" for name, count in (team_workload or {}).items())
        prompt = f"""Based on the following task and team workload, suggest the BEST team member to assign this task to.
Consider workload balance and likely expertise.

Task: {task_title}
Category: {task_category or 'General'}
Priority: {task_priority}

Team workload:
{workload_str}

Respond with ONLY the team member's name, nothing else."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"AI suggest assignee error: {e}")
            return ""

    async def suggest_deadline(self, task_title: str, task_priority: str = "medium",
                                avg_completion_days: float = 3.0) -> str:
        """Use AI to suggest a deadline for a task."""
        from datetime import datetime, timezone, timedelta
        prompt = f"""Suggest an appropriate deadline for this task. Consider the priority and average completion time.

Task: {task_title}
Priority: {task_priority}
Average completion time: {avg_completion_days} days

Respond with ONLY the number of days from now (e.g., "3" for 3 days). Nothing else."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=20,
                messages=[{"role": "user", "content": prompt}],
            )
            days_str = response.content[0].text.strip()
            days = int(''.join(c for c in days_str if c.isdigit()) or '3')
            deadline = datetime.now(timezone.utc) + timedelta(days=max(1, days))
            return deadline.isoformat()
        except Exception as e:
            logger.error(f"AI suggest deadline error: {e}")
            from datetime import datetime, timezone, timedelta
            return (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()



    async def analyze_content(self, content: str, prompt: str) -> str:
        """Analyze text content with a given prompt."""
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": f"{prompt}\n\n{content}"}],
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.error(f"AI analyze content error: {e}")
            return "Analysis not available"


ai_engine = AIEngine()
