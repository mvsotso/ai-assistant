"""
Migration: Add Task Groups & Sub Groups
Run this to add the new tables and columns for hierarchical task categorization.

Usage on VM:
  docker exec -it ai-assistant-app python -c "
  import asyncio
  from app.core.database import engine
  async def migrate():
      from sqlalchemy import text
      async with engine.begin() as conn:
          # Create task_groups table
          await conn.execute(text('''
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
          '''))

          # Create task_subgroups table
          await conn.execute(text('''
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
          '''))

          # Add group_id and subgroup_id columns to tasks table (if not exist)
          await conn.execute(text('''
              DO $$
              BEGIN
                  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='group_id') THEN
                      ALTER TABLE tasks ADD COLUMN group_id INTEGER REFERENCES task_groups(id) ON DELETE SET NULL;
                  END IF;
                  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='subgroup_id') THEN
                      ALTER TABLE tasks ADD COLUMN subgroup_id INTEGER REFERENCES task_subgroups(id) ON DELETE SET NULL;
                  END IF;
              END $$
          '''))

          # Create indexes
          await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_tasks_group_id ON tasks(group_id)'))
          await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_tasks_subgroup_id ON tasks(subgroup_id)'))
          await conn.execute(text('CREATE INDEX IF NOT EXISTS idx_task_subgroups_group_id ON task_subgroups(group_id)'))

          print('✅ Migration complete: task_groups, task_subgroups tables created, tasks table updated')

  asyncio.run(migrate())
  "
"""

# This file documents the migration SQL.
# The actual migration runs via the auto-migrate logic in main.py
# or can be run manually with the command above.

MIGRATION_SQL = """
-- Task Groups table
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
);

-- Task Sub Groups table
CREATE TABLE IF NOT EXISTS task_subgroups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    group_id INTEGER NOT NULL REFERENCES task_groups(id) ON DELETE CASCADE,
    sort_order INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Add columns to tasks table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='group_id') THEN
        ALTER TABLE tasks ADD COLUMN group_id INTEGER REFERENCES task_groups(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='subgroup_id') THEN
        ALTER TABLE tasks ADD COLUMN subgroup_id INTEGER REFERENCES task_subgroups(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_group_id ON tasks(group_id);
CREATE INDEX IF NOT EXISTS idx_tasks_subgroup_id ON tasks(subgroup_id);
CREATE INDEX IF NOT EXISTS idx_task_subgroups_group_id ON task_subgroups(group_id);
"""
