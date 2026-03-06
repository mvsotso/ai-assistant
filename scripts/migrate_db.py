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
