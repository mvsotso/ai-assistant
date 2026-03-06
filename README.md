# AI Personal Assistant

A personal AI assistant platform integrating **Telegram**, **Google Calendar**, and **collaborative task management** — powered by **Claude AI Opus 4.6**.

**Live:** https://sotso-assistant.duckdns.org  
**Bot:** @sotso_assistant_bot on Telegram

## Quick Start

### Prerequisites
- Google Cloud VM (e2-standard-2, Ubuntu 24.04)
- Domain name (free: duckdns.org)
- Telegram Bot Token (from @BotFather)
- Anthropic API Key (from console.anthropic.com)
- Google OAuth2 credentials (from GCP Console)

### Deploy in One Command

```bash
git clone https://github.com/mvsotso/ai-assistant.git
cd ai-assistant
bash scripts/deploy-gcp.sh sotso-assistant.duckdns.org mvsotso@gmail.com
```

The script handles Docker installation, SSL certificates, and service deployment.

### Manual Deploy

```bash
# 1. Clone and configure
git clone https://github.com/mvsotso/ai-assistant.git
cd ai-assistant
cp config/.env.example .env
# Edit .env with your API keys (use vim or sed commands)

# 2. Update nginx domain
sed -i 's/YOUR_DOMAIN.com/your-domain.duckdns.org/g' nginx/nginx.conf

# 3. Get SSL certificate
mkdir -p nginx/ssl
sudo docker run --rm -p 80:80 -v $(pwd)/nginx/ssl:/etc/letsencrypt \
  certbot/certbot certonly --standalone -d your-domain.duckdns.org \
  --email your@email.com --agree-tos --no-eff-email

# 4. Fix SSL permissions (important!)
sudo chmod -R 755 nginx/ssl
sudo chown -R $USER:$USER nginx/ssl

# 5. Build and start
docker compose -f docker-compose.prod.yml up -d --build

# 6. Register Telegram webhook
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.duckdns.org/api/v1/webhook/telegram"}'
```

## Architecture

```
ai-assistant/
├── app/
│   ├── main.py                # FastAPI entry point (auto-migrates DB on startup)
│   ├── core/
│   │   ├── config.py          # Environment configuration
│   │   ├── database.py        # PostgreSQL async connection
│   │   └── security.py        # Auth utilities
│   ├── models/                # SQLAlchemy models (User, Message, Task, Reminder)
│   ├── api/
│   │   ├── router.py          # REST API endpoints
│   │   └── calendar_api.py    # Google Calendar OAuth + REST
│   ├── services/
│   │   ├── ai_engine.py       # Claude AI integration
│   │   ├── telegram.py        # Telegram bot service
│   │   ├── calendar_svc.py    # Google Calendar service
│   │   ├── task_svc.py        # Task management
│   │   └── reminder_svc.py    # Reminder service
│   ├── bot/
│   │   ├── handlers.py        # Telegram command handlers
│   │   └── calendar_cmds.py   # Calendar bot commands
│   └── worker.py              # Celery background tasks
├── config/.env.example        # Environment template (Docker-ready defaults)
├── nginx/nginx.conf           # Reverse proxy + SSL
├── scripts/
│   ├── deploy-gcp.sh          # One-command deployment
│   ├── init_db.py             # Database initialization
│   └── migrate_db.py          # Database migrations
├── docker-compose.prod.yml    # Production (app + DB + Redis + Celery + Nginx)
├── docker-compose.yml         # Development
└── Dockerfile
```

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Register your account |
| `/help` | Show all commands |
| `/status` | Your task stats |
| `/summary` | Summarize group messages (AI) |
| `/task add <title>` | Create a task |
| `/task list` | List your tasks |
| `/task done <id>` | Complete a task |
| `/task assign <id> @user` | Assign to team member |
| `/remind <min> <msg>` | Set a reminder |
| `/connect` | Link Google Calendar |
| `/today` | Today's schedule |
| `/week` | 7-day schedule |
| `/free` | Find free time slots |
| `/event <title> at <time> for <dur>` | Create event |
| `/cancel <name>` | Cancel an event |
| Any message (private chat) | AI conversation |

## Common Issues & Fixes

| Issue | Cause | Fix |
|-------|-------|-----|
| `version is obsolete` warning | Old docker-compose format | Already fixed — `version` removed |
| `password authentication failed` | DB password mismatch | Ensure DATABASE_URL password matches DB_PASSWORD |
| `502 Bad Gateway` | App not started yet | Wait 15s, check `docker compose logs app` |
| SSL `permission denied` | Certbot creates root-owned files | `sudo chmod -R 755 nginx/ssl && sudo chown -R $USER:$USER nginx/ssl` |
| `redirect_uri_mismatch` | URI not registered in GCP | Add `https://domain/api/v1/calendar/auth/callback` in GCP Credentials |
| `access_denied` on Google auth | Email not in test users | Add your email in GCP OAuth consent screen → Test users |
| `google_token` column missing | DB created before code update | Auto-fixed on startup, or run `scripts/migrate_db.py` |
| `listen ... http2` deprecated | Old nginx directive | Already fixed — uses `http2 on;` directive |
| `localhost` in .env | Docker needs container names | Use `db` for PostgreSQL, `redis` for Redis, NOT `localhost` |
| AI chat error `credit balance too low` | No Anthropic credits | Add credits at console.anthropic.com/settings/billing |

## Environment Variables

**CRITICAL:** In Docker, use container names not `localhost`:
- Database host: `db` (not `localhost`)
- Redis host: `redis` (not `localhost`)

See `config/.env.example` for the complete reference with comments.

## License

Private project — Sot So © 2026
