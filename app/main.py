"""
AI Personal Assistant — FastAPI Application
Main entry point for the application.
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.database import init_db, close_db, engine
from app.api.router import router
from app.api.calendar_api import calendar_router
from app.api.recurring_api import recurring_router
from app.api.task_group_api import router as task_group_router
from app.api.category_api import router as category_router
from app.api.team_api import router as team_mgmt_router
from app.api.task_action_api import router as task_action_router
from app.api.dependency_api import router as dependency_router
from app.api.auth import auth_router
from app.models.recurring_task import RecurringTask  # noqa: ensure table creation
from app.models.task_group import TaskGroup, TaskSubGroup  # noqa: ensure table creation
from app.models.team_role import TeamRole  # noqa: ensure table creation
from app.models.task_action import TaskAction  # noqa: ensure table creation
from app.models.task_dependency import TaskDependency  # noqa: ensure table creation
from app.models.push_subscription import PushSubscription  # noqa: ensure table creation
from app.models.email_preference import EmailPreference  # noqa: ensure table creation
from app.models.system_setting import SystemSetting  # noqa: ensure table creation
from app.models.task_template import TaskTemplate  # noqa: ensure table creation
from app.models.saved_report import SavedReport  # noqa: ensure table creation
from app.models.workflow_rule import WorkflowRule  # noqa: ensure table creation
from app.models.task_file import TaskFile  # noqa: ensure table creation
from app.models.time_log import TimeLog  # noqa: ensure table creation
from app.models.collaboration import TaskWatcher, ActivityLog  # noqa: ensure table creation

settings = get_settings()

# ── Rate Limiter (Redis-backed) ──
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=settings.redis_url,
    default_limits=["60/minute"],
)

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

    # Security: warn if default secret key is in use
    if settings.app_secret_key == "change-this-to-a-random-secret-key":
        if settings.is_production:
            raise RuntimeError("FATAL: app_secret_key is set to the default value. Set APP_SECRET_KEY in .env before running in production.")
        logger.warning("⚠️ SECURITY: Using default app_secret_key — set APP_SECRET_KEY in .env for production!")

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
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=:tbl AND column_name=:col"
                ).bindparams(tbl=table, col=col))
                if not result.fetchall():
                    await conn.execute(text(sql))
                    logger.info(f"🔧 Added {col} column to {table} table")

            # ── Task Groups migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_groups (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    icon VARCHAR(10) DEFAULT '📁',
                    color VARCHAR(7) DEFAULT '#3b82f6',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    creator_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_subgroups (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    group_id INTEGER NOT NULL REFERENCES task_groups(id) ON DELETE CASCADE,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='group_id') THEN
                        ALTER TABLE tasks ADD COLUMN group_id INTEGER REFERENCES task_groups(id) ON DELETE SET NULL;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='subgroup_id') THEN
                        ALTER TABLE tasks ADD COLUMN subgroup_id INTEGER REFERENCES task_subgroups(id) ON DELETE SET NULL;
                    END IF;
                END $$
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_tasks_group_id ON tasks(group_id)'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_tasks_subgroup_id ON tasks(subgroup_id)'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_subgroups_group_id ON task_subgroups(group_id)'))
            logger.info("🔧 Task groups migration checked")
            # ── Categories migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS categories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    icon VARCHAR(10) DEFAULT '📂',
                    color VARCHAR(7) DEFAULT '#3b82f6',
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS subcategories (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                    sort_order INTEGER DEFAULT 0,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_subcategories_category_id ON subcategories(category_id)'))
            # Seed predefined categories if table is empty
            seed_check = await conn.execute(text("SELECT COUNT(*) FROM categories"))
            if seed_check.scalar() == 0:
                seed_cats = [
                    ("Administration", "🏢", "#6366f1"),
                    ("Data Management", "📊", "#3b82f6"),
                    ("IT & Systems", "💻", "#10b981"),
                    ("Tax Operations", "💰", "#f59e0b"),
                    ("Project Management", "📋", "#8b5cf6"),
                    ("Communication", "📢", "#ec4899"),
                    ("Research", "🔍", "#14b8a6"),
                ]
                seed_subs = {
                    "Administration": ["HR", "Finance", "Procurement", "Legal", "General Affairs"],
                    "Data Management": ["ETL", "Data Quality", "Database", "Data Governance", "Reporting"],
                    "IT & Systems": ["Infrastructure", "Development", "Security", "Support", "Networking"],
                    "Tax Operations": ["Audit", "Compliance", "Collection", "Registration", "Enforcement"],
                    "Project Management": ["Planning", "Execution", "Monitoring", "Evaluation", "Closure"],
                    "Communication": ["Internal", "External", "Media", "Events", "Training"],
                    "Research": ["Policy", "Analysis", "Statistics", "Survey", "Documentation"],
                }
                for idx, (name, icon, color) in enumerate(seed_cats):
                    await conn.execute(text(
                        "INSERT INTO categories (name, icon, color, sort_order) VALUES (:n, :i, :c, :s)"
                    ), {"n": name, "i": icon, "c": color, "s": idx})
                    cat_row = await conn.execute(text("SELECT id FROM categories WHERE name = :n"), {"n": name})
                    cat_id = cat_row.scalar()
                    for si, sub_name in enumerate(seed_subs.get(name, [])):
                        await conn.execute(text(
                            "INSERT INTO subcategories (name, category_id, sort_order) VALUES (:n, :cid, :s)"
                        ), {"n": sub_name, "cid": cat_id, "s": si})
                logger.info("🌱 Seeded 7 predefined categories with subcategories")
            logger.info("🔧 Categories migration checked")


            # ── Team Roles migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS team_roles (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL UNIQUE,
                    description TEXT,
                    color VARCHAR(7) DEFAULT '#3b82f6',
                    permissions TEXT,
                    is_default BOOLEAN DEFAULT FALSE,
                    sort_order INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """))

            # Add new columns to users table
            user_migrations = [
                ("users", "role_id", "ALTER TABLE users ADD COLUMN role_id INTEGER REFERENCES team_roles(id) ON DELETE SET NULL"),
                ("users", "phone", "ALTER TABLE users ADD COLUMN phone VARCHAR(50)"),
                ("users", "email", "ALTER TABLE users ADD COLUMN email VARCHAR(255)"),
                ("users", "avatar_url", "ALTER TABLE users ADD COLUMN avatar_url TEXT"),
                ("users", "notes", "ALTER TABLE users ADD COLUMN notes TEXT"),
                ("users", "department", "ALTER TABLE users ADD COLUMN department VARCHAR(100)"),
                ("users", "title", "ALTER TABLE users ADD COLUMN title VARCHAR(200)"),
            ]
            for table, col, sql in user_migrations:
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=:tbl AND column_name=:col"
                ).bindparams(tbl=table, col=col))
                if not result.fetchall():
                    await conn.execute(text(sql))
                    logger.info(f"🔧 Added {col} column to {table} table")

            # Seed default roles if none exist
            role_count = await conn.execute(text("SELECT COUNT(*) FROM team_roles"))
            if (role_count.scalar() or 0) == 0:
                await conn.execute(text("""
                    INSERT INTO team_roles (name, description, color, permissions, is_default, sort_order) VALUES
                    ('Admin', 'Full access to all features', '#ef4444', '["view","edit","admin","delete"]', FALSE, 1),
                    ('Editor', 'Can view and edit tasks and content', '#3b82f6', '["view","edit"]', TRUE, 2),
                    ('Viewer', 'Read-only access', '#22c55e', '["view"]', FALSE, 3)
                """))
                logger.info("🔧 Seeded default team roles: Admin, Editor, Viewer")

            logger.info("🔧 Team roles migration checked")

            # ── Task Actions migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_actions (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    title VARCHAR(500) NOT NULL,
                    description TEXT,
                    is_done BOOLEAN DEFAULT FALSE,
                    sort_order INTEGER DEFAULT 0,
                    assignee_name VARCHAR(255),
                    assignee_id BIGINT,
                    due_date TIMESTAMPTZ,
                    completed_at TIMESTAMPTZ,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_actions_task_id ON task_actions(task_id)'))
            logger.info("🔧 Task actions migration checked")

            # ── Task Dependencies migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    depends_on_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    dep_type VARCHAR(20) DEFAULT 'blocks',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT uq_task_dependency UNIQUE (task_id, depends_on_id),
                    CONSTRAINT chk_no_self_dep CHECK (task_id != depends_on_id)
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_dep_task_id ON task_dependencies(task_id)'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_dep_depends_on ON task_dependencies(depends_on_id)'))
            logger.info("🔧 Task dependencies migration checked")

            # ── Notifications migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    type VARCHAR(50) NOT NULL,
                    title VARCHAR(500) NOT NULL,
                    message TEXT,
                    link VARCHAR(500),
                    entity_id INTEGER,
                    entity_type VARCHAR(50),
                    is_read BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_notif_user_read ON notifications(user_id, is_read)'))
            logger.info("🔧 Notifications migration checked")


            # ── Audit Logs migration ──
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL,
                    user_email VARCHAR(255),
                    action VARCHAR(50) NOT NULL,
                    field_changed VARCHAR(100),
                    old_value TEXT,
                    new_value TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_audit_logs_task_id ON audit_logs(task_id)'))
            logger.info("🔧 Audit logs migration checked")
            # ── Reminder Enhancement migration (Phase 16) ──
            reminder_migrations = [
                ("reminders", "task_id", "ALTER TABLE reminders ADD COLUMN task_id INTEGER"),
                ("reminders", "event_id", "ALTER TABLE reminders ADD COLUMN event_id VARCHAR(500)"),
                ("reminders", "snooze_count", "ALTER TABLE reminders ADD COLUMN snooze_count INTEGER DEFAULT 0"),
                ("reminders", "original_remind_at", "ALTER TABLE reminders ADD COLUMN original_remind_at TIMESTAMPTZ"),
                ("reminders", "telegram_message_id", "ALTER TABLE reminders ADD COLUMN telegram_message_id BIGINT"),
            ]
            for table, col, sql in reminder_migrations:
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=:tbl AND column_name=:col"
                ).bindparams(tbl=table, col=col))
                if not result.fetchall():
                    await conn.execute(text(sql))
                    logger.info(f"🔧 Added {col} column to {table} table")
            logger.info("🔧 Reminder enhancement migration checked")

            # -- Push Subscriptions migration (Phase 18) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS push_subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_email VARCHAR(255) NOT NULL,
                    endpoint VARCHAR(2000) NOT NULL UNIQUE,
                    p256dh VARCHAR(200) NOT NULL,
                    auth VARCHAR(200) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_push_subs_email ON push_subscriptions(user_email)'))

            # -- Email Preferences migration (Phase 19) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS email_preferences (
                    id SERIAL PRIMARY KEY,
                    user_email VARCHAR(255) UNIQUE NOT NULL,
                    email_enabled BOOLEAN DEFAULT TRUE,
                    task_assigned BOOLEAN DEFAULT TRUE,
                    task_status_change BOOLEAN DEFAULT TRUE,
                    reminder_due BOOLEAN DEFAULT TRUE,
                    daily_summary BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_email_prefs_email ON email_preferences(user_email)'))
            logger.info('Email preferences migration checked')

            # -- System Settings migration (settings UI) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    id SERIAL PRIMARY KEY,
                    key VARCHAR(100) UNIQUE NOT NULL,
                    value TEXT,
                    is_secret BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_system_settings_key ON system_settings(key)'))
            logger.info('System settings migration checked')

            # -- Task Templates migration (Phase 20) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_templates (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL UNIQUE,
                    description_text TEXT,
                    icon VARCHAR(10) DEFAULT '📋',
                    color VARCHAR(7) DEFAULT '#3b82f6',
                    title_template VARCHAR(500) NOT NULL,
                    priority VARCHAR(50) DEFAULT 'medium',
                    status VARCHAR(50) DEFAULT 'todo',
                    category VARCHAR(100),
                    subcategory VARCHAR(100),
                    assignee_name VARCHAR(255),
                    label VARCHAR(100),
                    due_offset_hours INTEGER,
                    group_id INTEGER,
                    subgroup_id INTEGER,
                    checklist_json TEXT,
                    is_builtin BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    sort_order INTEGER DEFAULT 0,
                    use_count INTEGER DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_templates_active ON task_templates(is_active)'))
            logger.info('Task templates migration checked')

            # Seed default templates if table is empty
            tmpl_count = await conn.execute(text("SELECT COUNT(*) FROM task_templates"))
            if tmpl_count.scalar() == 0:
                seed_templates = [
                    ("Meeting Follow-Up", "📨", "#3b82f6", "Follow up: {title}", "Follow up on action items from the meeting.", "high", "todo", 24, '[{"title":"Review meeting notes"},{"title":"Send summary email"},{"title":"Schedule next meeting"}]'),
                    ("Weekly Report", "📝", "#22c55e", "Weekly Report - {date}", "Prepare and submit the weekly progress report.", "medium", "todo", 168, '[{"title":"Collect team updates"},{"title":"Compile statistics"},{"title":"Write summary"},{"title":"Submit to management"}]'),
                    ("Bug Fix", "🐛", "#ef4444", "Fix: {title}", "Investigate and resolve the reported bug.", "high", "todo", 48, '[{"title":"Reproduce the issue"},{"title":"Identify root cause"},{"title":"Implement fix"},{"title":"Test fix"},{"title":"Deploy"}]'),
                    ("Document Review", "📄", "#a855f7", "Review: {title}", "Review the document and provide feedback.", "medium", "todo", 72, '[{"title":"Read document thoroughly"},{"title":"Add comments"},{"title":"Prepare feedback summary"}]'),
                    ("New Initiative", "🚀", "#f97316", "{title}", "Plan and launch a new initiative or project.", "high", "todo", 168, '[{"title":"Define scope and objectives"},{"title":"Identify stakeholders"},{"title":"Create timeline"},{"title":"Assign team members"},{"title":"Kick-off meeting"}]'),
                ]
                for i, (name, icon, color, title_tmpl, desc, prio, status, offset, checklist) in enumerate(seed_templates):
                    await conn.execute(text(
                        "INSERT INTO task_templates (name, icon, color, title_template, description_text, priority, status, due_offset_hours, checklist_json, is_builtin, sort_order) "
                        "VALUES (:name, :icon, :color, :title_tmpl, :desc, :prio, :status, :offset, :checklist, TRUE, :sort)"
                    ), {"name": name, "icon": icon, "color": color, "title_tmpl": title_tmpl, "desc": desc, "prio": prio, "status": status, "offset": offset, "checklist": checklist, "sort": i})
                logger.info("Seeded 5 default task templates")


            # -- Saved Reports migration (Phase 25) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS saved_reports (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    report_type VARCHAR(50) NOT NULL DEFAULT 'status_summary',
                    filters_json TEXT,
                    schedule VARCHAR(20) DEFAULT 'none',
                    recipients_json TEXT,
                    last_run_at TIMESTAMPTZ,
                    creator_email VARCHAR(255),
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_saved_reports_active ON saved_reports(is_active)'))
            logger.info('Saved reports migration checked')


            # -- Workflow Rules migration (Phase 26) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_rules (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    trigger VARCHAR(50) NOT NULL,
                    condition_json TEXT,
                    action_type VARCHAR(50) NOT NULL,
                    action_config_json TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    creator_email VARCHAR(255),
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_workflow_rules_active ON workflow_rules(is_active)'))
            logger.info('Workflow rules migration checked')


            # -- Task Files migration (Phase 27) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_files (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
                    filename VARCHAR(500) NOT NULL,
                    original_filename VARCHAR(500) NOT NULL,
                    file_size BIGINT DEFAULT 0,
                    mime_type VARCHAR(200),
                    storage_path VARCHAR(1000) NOT NULL,
                    uploader_email VARCHAR(255),
                    description TEXT,
                    ai_summary TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_files_task_id ON task_files(task_id)'))
            logger.info('Task files migration checked')


            # -- Time Logs migration (Phase 28) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS time_logs (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_email VARCHAR(255),
                    description TEXT,
                    started_at TIMESTAMPTZ,
                    ended_at TIMESTAMPTZ,
                    duration_minutes FLOAT DEFAULT 0,
                    is_running BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_time_logs_task_id ON time_logs(task_id)'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_time_logs_user ON time_logs(user_email)'))
            logger.info('Time logs migration checked')

            # Add estimated_hours to tasks
            est_check = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='tasks' AND column_name='estimated_hours'"
            ))
            if not est_check.fetchall():
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN estimated_hours FLOAT"))
                logger.info('Added estimated_hours column to tasks')


            # -- Collaboration migration (Phase 29) --
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS task_watchers (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    user_email VARCHAR(255) NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    CONSTRAINT uq_task_watcher UNIQUE (task_id, user_email)
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_watchers_task ON task_watchers(task_id)'))
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS activity_logs (
                    id SERIAL PRIMARY KEY,
                    entity_type VARCHAR(50) NOT NULL,
                    entity_id INTEGER,
                    action VARCHAR(50) NOT NULL,
                    user_email VARCHAR(255),
                    details_json TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at DESC)'))
            await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_activity_logs_entity ON activity_logs(entity_type, entity_id)'))
            logger.info('Collaboration migration checked')

            # Add version and last_modified_by to tasks
            collab_cols = [
                ("tasks", "version", "ALTER TABLE tasks ADD COLUMN version INTEGER DEFAULT 1"),
                ("tasks", "last_modified_by", "ALTER TABLE tasks ADD COLUMN last_modified_by VARCHAR(255)"),
            ]
            for table, col, sql in collab_cols:
                result = await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name=:tbl AND column_name=:col"
                ).bindparams(tbl=table, col=col))
                if not result.fetchall():
                    await conn.execute(text(sql))
                    logger.info(f'Added {col} column to {table} table')

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

# ── Rate Limiting ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS — restrict to trusted origins
_cors_origins = [
    "https://aia.rikreay24.com",
    "https://sotso-assistant.duckdns.org",
    "http://localhost:8000",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://localhost:8181",
    "http://localhost:8282",
    "http://localhost:8383",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8181",
    "http://127.0.0.1:8282",
    "http://127.0.0.1:8383",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routes
from app.api.notification_api import notification_router, notification_public_router  # noqa
from app.api.settings_api import settings_router  # noqa
from app.api.template_api import router as template_router  # noqa
from app.api.report_api import router as report_router  # noqa
from app.api.workflow_api import router as workflow_router  # noqa
from app.api.file_api import router as file_router  # noqa
from app.api.time_api import router as time_router  # noqa
from app.api.collab_api import router as collab_router  # noqa
app.include_router(router)
app.include_router(calendar_router)
app.include_router(recurring_router)
app.include_router(task_group_router)
app.include_router(category_router)
app.include_router(team_mgmt_router)
app.include_router(task_action_router)
app.include_router(dependency_router)
app.include_router(auth_router)
app.include_router(notification_router)
app.include_router(notification_public_router)
app.include_router(settings_router)
app.include_router(template_router)
app.include_router(report_router)
app.include_router(workflow_router)
app.include_router(file_router)
app.include_router(time_router)
app.include_router(collab_router)


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


@app.get("/sw.js")
async def service_worker():
    """Serve service worker from root scope."""
    import os
    from fastapi.responses import Response
    sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
    if os.path.exists(sw_path):
        with open(sw_path, "r") as f:
            return Response(content=f.read(), media_type="application/javascript",
                            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})
    return Response(status_code=404)
