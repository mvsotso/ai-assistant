# AI Personal Assistant — Claude Code Context

## Project Overview
Personal AI assistant platform for Sot So (Chief of Data Management Bureau, GDT Cambodia).
Deployed at https://aia.rikreay24.com (primary) and https://sotso-assistant.duckdns.org (legacy).
Telegram bot @sotso_assistant_bot.

## Tech Stack
- **Backend:** Python 3.11, FastAPI, SQLAlchemy (async), asyncpg
- **Database:** PostgreSQL 16
- **Cache/Queue:** Redis 7, Celery
- **AI:** Claude Opus 4.6 via Anthropic API
- **Frontend:** Single-file vanilla HTML/CSS/JS at `app/static/index.html` (~2950 lines)
- **Calendar:** Google Calendar + Drive API with OAuth2
- **Bot:** Telegram Bot API via httpx (webhook mode)
- **Deploy:** Docker Compose on GCP VM (asia-southeast1-b), CI/CD via GitHub Actions
- **SSL:** Let's Encrypt via Certbot, Nginx reverse proxy
- **DNS:** Cloudflare DNS (rikreay24.com), DuckDNS (legacy)

## Project Structure
```
app/
├── main.py                  # FastAPI entry + auto-migrations
├── core/config.py           # Pydantic settings from .env
├── core/database.py         # Async SQLAlchemy engine
├── models/                  # SQLAlchemy models
│   ├── task.py              # Task (status, priority, group_id, subgroup_id)
│   ├── task_dependency.py   # TaskDependency (blocks/blocked-by)
│   ├── task_action.py       # TaskAction (checklist items)
│   ├── task_group.py        # TaskGroup + TaskSubGroup
│   ├── team_role.py         # TeamRole
│   ├── audit_log.py         # AuditLog (task change tracking)
│   ├── category.py          # Category + Subcategory (CRUD)
│   ├── reminder.py          # Reminder (snooze, task linking, datetime)
│   ├── user.py, message.py, comment.py, recurring_task.py
├── api/
│   ├── router.py            # Main API: tasks, board, dashboard, messages, reminders, AI chat
│   ├── calendar_api.py      # Google Calendar CRUD
│   ├── dependency_api.py    # Task dependencies with circular detection
│   ├── task_action_api.py   # Task actions/checklist
│   ├── task_group_api.py    # Task groups & subgroups
│   ├── team_api.py          # Team management
│   ├── recurring_api.py     # Recurring tasks
│   ├── category_api.py      # Category & subcategory CRUD
│   └── auth.py              # Google OAuth + HMAC sessions
├── services/
│   ├── ai_engine.py         # Claude integration with action extraction
│   ├── action_executor.py   # Executes AI actions (events, tasks, reminders)
│   ├── calendar_svc.py      # Google Calendar + Drive
│   ├── task_svc.py          # Task CRUD, board, stats
│   └── file_processor.py    # PDF, Excel, Word, CSV, image extraction
├── bot/handlers.py          # Telegram bot commands + callback queries
├── static/index.html        # Full web dashboard (single file)
└── worker.py                # Celery workers
```

## Key Architecture Decisions
- **Single HTML file** for dashboard — all CSS, HTML, JS in `app/static/index.html`
- **Auto-migrations** in `main.py` lifespan — CREATE TABLE IF NOT EXISTS + ALTER TABLE for new columns
- **i18n** — 220+ keys in `I18N` object (EN/KH), `data-i18n` attributes, `t('key')` helper function
- **Noto Sans Khmer** Google Font for Khmer language support
- **Chart.js** with Cloudflare CDN fallback for analytics
- **AI-embedded actions** in Task Detail Modal and Event Modal

## Database
PostgreSQL with tables: users, messages, tasks, reminders, task_comments, recurring_tasks, task_groups, task_subgroups, team_roles, task_actions, task_dependencies, notifications, categories, subcategories, audit_logs, push_subscriptions, email_preferences

## Deployment
```bash
git push  # CI/CD auto-deploys via GitHub Actions SSH
```
Manual: `docker compose -f docker-compose.prod.yml up -d --build`

GCP VM: instance-20260306-035055, IP: 34.124.208.176 (ephemeral)
Domain: aia.rikreay24.com (Cloudflare DNS, rikreay24.com)
DuckDNS (legacy): sotso-assistant.duckdns.org


## Coding Preferences
- Always edit original files directly (not patch files)
- Comprehensive solutions over minimal examples
- Add auto-migration SQL in main.py for new tables/columns
- Add i18n keys (both EN and KH) for any new UI text
- Keep emojis outside `data-i18n` spans to prevent double-emoji on language toggle
- Use `I18N[curLang].key` for JS-rendered text, `data-i18n="key"` for static HTML
- Test by pushing to git (CI/CD deploys automatically)

## Current Features (Phases 1-19)
Telegram bot, Google Calendar/Drive, AI chat with file upload and conversation memory, task management with groups/subgroups, team management with roles and Excel bulk import, task actions/checklist, task dependencies (blocks/blocked-by), recurring tasks (matching normal task form), analytics with 6 Chart.js charts + AI insights, global search (Ctrl+K), full EN/KH i18n, AI-embedded actions in tasks (follow up, progress check, summary, delegate) and events (key notes, agenda, prep brief, follow up, auto-keynotes from attachments), smart event creation from messages with field validation, Set Reminder from messages with AI extraction, assignee dropdown with team member suggestions, fully interactive dashboard with clickable everything, category & subcategory CRUD management, enhanced reminders with datetime picker + snooze (web & Telegram inline buttons) + task linking + recurring reminders, notification badge system, MoM processor, task audit log with history view, reminder history tab, KPI dashboard cards (avg completion, on-time rate, overdue, weekly), burndown chart, AI task suggestions, prompt library (quick prompts in AI chat), smart reminder timing (AI-suggested), Gantt chart with dependency arrows (SVG) + drag-to-reschedule + critical path highlighting + milestones + category filter, analytics export (CSV/PNG), trend comparison (vs previous period), RBAC with require_permission decorator, web push notifications (VAPID), email notifications (SMTP with per-user preferences), complete API rate limiting (slowapi on all endpoints).

## Infrastructure Notes
- **Docker MTU:** Must be 1460 to match GCP network MTU (configured in `docker-compose.prod.yml` networks section)
- **Service Worker:** `app/static/sw.js` uses cache-first strategy; bump `CACHE_VERSION` when updating `index.html`
- **Google Login:** Dual approach — GIS library (primary) + OAuth redirect fallback (`/api/v1/auth/google/callback`)
- **Google OAuth Redirect URI:** `https://aia.rikreay24.com/api/v1/auth/google/callback` (also keeps duckdns as fallback)
- **IP changes:** If VM IP changes (ephemeral), update DuckDNS, Telegram webhook, and Google OAuth redirect URI
- **Workplace WiFi:** May block the site — enable Cloudflare Proxy (orange cloud) + Chrome Secure DNS (Cloudflare 1.1.1.1)
- **Cloudflare Proxy:** Enabled (orange cloud) on aia.rikreay24.com A record; SSL mode = Full
- **Service Worker cache:** Currently at v23 — bump on every frontend change
- **Edit/Write tool workaround:** EEXIST errors on Edit/Write tools — use Python scripts in `C:\Users\Dell\AppData\Local\Temp\` executed via Bash

## What To Work On Next
1. Flutter mobile app
2. Task templates / quick-create presets
3. Dependency graph visualization (mermaid.js or vis.js)
4. AI attachment content analysis (fetch Drive file content)
5. Offline sync improvements (IndexedDB persistence, Background Sync API)
6. Reserve static IP in GCP to avoid IP changes on VM restart
8. Task templates / quick-create presets
