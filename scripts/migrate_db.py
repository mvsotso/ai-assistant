"""
Database migration script — adds missing columns to existing tables.
Run this after upgrading: python scripts/migrate_db.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine
from sqlalchemy import text


MIGRATIONS = [
    {
        "name": "Add google_token column to users table",
        "check": "SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='google_token'",
        "sql": "ALTER TABLE users ADD COLUMN google_token TEXT",
    },
    {
        "name": "Add label column to tasks table",
        "check": "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='label'",
        "sql": "ALTER TABLE tasks ADD COLUMN label VARCHAR(100)",
    },
    {
        "name": "Create task_comments table",
        "check": "SELECT table_name FROM information_schema.tables WHERE table_name='task_comments'",
        "sql": """CREATE TABLE IF NOT EXISTS task_comments (
            id SERIAL PRIMARY KEY,
            task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            user_name VARCHAR(255),
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )""",
    },
    {
        "name": "Add index on task_comments.task_id",
        "check": "SELECT indexname FROM pg_indexes WHERE tablename='task_comments' AND indexname='ix_task_comments_task_id'",
        "sql": "CREATE INDEX ix_task_comments_task_id ON task_comments(task_id)",
    },
    {
        "name": "Add category column to tasks table",
        "check": "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='category'",
        "sql": "ALTER TABLE tasks ADD COLUMN category VARCHAR(100)",
    },
    {
        "name": "Add subcategory column to tasks table",
        "check": "SELECT column_name FROM information_schema.columns WHERE table_name='tasks' AND column_name='subcategory'",
        "sql": "ALTER TABLE tasks ADD COLUMN subcategory VARCHAR(100)",
    },
]


async def main():
    print("🔧 Running database migrations...")
    async with engine.begin() as conn:
        for m in MIGRATIONS:
            # Check if migration is needed
            result = await conn.execute(text(m["check"]))
            rows = result.fetchall()
            if rows:
                print(f"  ✅ Already applied: {m['name']}")
            else:
                await conn.execute(text(m["sql"]))
                print(f"  🆕 Applied: {m['name']}")

    print("✅ All migrations complete!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
