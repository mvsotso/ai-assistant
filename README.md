# AI Personal Assistant

A personal AI assistant platform that integrates **Telegram**, **Google Calendar**, and **collaborative task management** — powered by **Claude AI**.

## Architecture

```
ai-assistant/
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── core/
│   │   ├── config.py         # Environment configuration
│   │   ├── database.py       # PostgreSQL connection + session management
│   │   └── security.py       # Authentication utilities
│   ├── models/
│   │   ├── base.py           # SQLAlchemy base
│   │   ├── user.py           # User model
│   │   ├── message.py        # Telegram message model
│   │   ├── task.py           # Task model
│   │   └── reminder.py       # Reminder model
│   ├── api/
│   │   ├── router.py         # API router aggregator
│   │   ├── health.py         # Health check endpoint
│   │   ├── tasks.py          # Task CRUD endpoints
│   │   └── webhook.py        # Telegram webhook endpoint
│   ├── services/
│   │   ├── telegram.py       # Telegram bot service
│   │   ├── calendar_svc.py   # Google Calendar service (Phase 2)
│   │   ├── task_svc.py       # Task management service
│   │   ├── ai_engine.py      # Claude AI integration
│   │   └── reminder_svc.py   # Reminder & notification service
│   └── bot/
│       ├── handlers.py       # Telegram command handlers
│       └── commands.py       # Bot command definitions
├── config/
│   └── .env.example          # Environment variable template
├── scripts/
│   └── init_db.py            # Database initialization script
├── tests/
│   └── test_health.py        # Basic tests
├── requirements.txt          # Python dependencies
├── Dockerfile                # Container build
├── docker-compose.yml        # Local dev with PostgreSQL + Redis
└── README.md                 # This file
```

## Quick Start

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 16
- Redis 7
- Telegram Bot Token (from @BotFather)
- Claude API Key (from console.anthropic.com)

### 2. Setup

```bash
# Clone the repo
git clone https://github.com/mvsotso/ai-assistant.git
cd ai-assistant

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp config/.env.example .env
# Edit .env with your API keys and database credentials

# Initialize database
python scripts/init_db.py

# Run the application
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Docker (Recommended)

```bash
# Start all services (app + PostgreSQL + Redis)
docker-compose up -d

# View logs
docker-compose logs -f app
```

### 4. Set Telegram Webhook

```bash
# After deploying to your server with HTTPS
curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-domain.com/api/v1/webhook/telegram"}'
```

## Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Initialize the bot and register your account |
| `/help` | Show available commands |
| `/status` | Show system status and your stats |
| `/summary` | Summarize recent messages in this group |
| `/send <group> <message>` | Send a message to a group on your behalf |
| `/remind <time> <message>` | Set a reminder |
| `/task add <title>` | Create a new task |
| `/task list` | List your pending tasks |
| `/task done <id>` | Mark a task as completed |
| `/today` | Show today's calendar (Phase 2) |
| `/free` | Find free time slots (Phase 2) |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health` | Health check |
| `POST` | `/api/v1/webhook/telegram` | Telegram webhook receiver |
| `GET` | `/api/v1/tasks` | List tasks |
| `POST` | `/api/v1/tasks` | Create task |
| `PATCH` | `/api/v1/tasks/{id}` | Update task |
| `DELETE` | `/api/v1/tasks/{id}` | Delete task |
| `POST` | `/api/v1/ai/chat` | AI assistant chat endpoint |

## Environment Variables

See `config/.env.example` for the full list. Key variables:

- `TELEGRAM_BOT_TOKEN` — From @BotFather
- `ANTHROPIC_API_KEY` — From console.anthropic.com
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string
- `ADMIN_TELEGRAM_ID` — Your Telegram user ID (for admin commands)

## Deployment

The app is designed for Google Cloud e2-standard-2 (Singapore region):

```bash
# On your GCP VM
git pull origin main
docker-compose -f docker-compose.prod.yml up -d
```

## License

Private project — Sot So © 2026
