"""
Database initialization script.
Run this to create all tables: python scripts/init_db.py
"""
import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import init_db, engine
from app.models import User, Message, Task, Reminder  # Import all models


async def main():
    print("🔧 Initializing database...")
    await init_db()
    print("✅ All tables created successfully!")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
