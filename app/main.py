"""
AI Personal Assistant — FastAPI Application
Main entry point for the application.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db, close_db, engine
from app.api.router import router
from app.api.calendar_api import calendar_router
from app.api.recurring_api import recurring_router
from app.api.auth import auth_router
from app.models.recurring_task import RecurringTask  # noqa: ensure table creation

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.app_debug else logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("🚀 Starting AI Personal Assistant...")
    await init_db()
    logger.info("✅ Database initialized")

    # Run migrations to add any missing columns
    try:
        from sqlalchemy import text
        async with engine.begin() as conn:
            migrations = [
                ("users", "google_token", "ALTER TABLE users ADD COLUMN google_token TEXT"),
                ("tasks", "label", "ALTER TABLE tasks ADD COLUMN label VARCHAR(100)"),
                ("tasks", "category", "ALTER TABLE tasks ADD COLUMN category VARCHAR(100)"),
                ("tasks", "subcategory", "ALTER TABLE tasks ADD COLUMN subcategory VARCHAR(100)"),
            ]
            for table, col, sql in migrations:
                result = await conn.execute(text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name='{table}' AND column_name='{col}'"
                ))
                if not result.fetchall():
                    await conn.execute(text(sql))
                    logger.info(f"🔧 Added {col} column to {table} table")
    except Exception as e:
        logger.warning(f"⚠️ Migration check: {e}")

    # Set Telegram webhook if configured
    if settings.webhook_url and settings.telegram_bot_token:
        from app.services.telegram import telegram_service
        try:
            result = await telegram_service.set_webhook(settings.webhook_url)
            logger.info(f"📡 Telegram webhook: {result}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to set webhook: {e}")

    logger.info(f"🟢 Assistant ready on {settings.app_host}:{settings.app_port}")

    yield

    # Shutdown
    logger.info("🔴 Shutting down...")
    await close_db()
    logger.info("Database connection closed")


app = FastAPI(
    title=settings.app_name,
    description="Personal AI Assistant with Telegram, Google Calendar, and Task Management",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_debug else None,
    redoc_url="/redoc" if settings.app_debug else None,
)

# CORS — allow all origins for dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routes
app.include_router(router)
app.include_router(calendar_router)
app.include_router(recurring_router)
app.include_router(auth_router)


@app.get("/")
async def root():
    """Serve the web dashboard."""
    import os
    html_path = os.path.join(os.path.dirname(__file__), "static", "index.html")
    if os.path.exists(html_path):
        from fastapi.responses import HTMLResponse
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    return {"name": settings.app_name, "status": "running"}
