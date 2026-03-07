"""
Team Management API
Full CRUD for roles and team members.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User
from app.models.team_role import TeamRole
from app.models.task import Task
from app.api.auth import require_auth
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter(prefix="/api/v1/team-mgmt", tags=["team-management"], dependencies=[Depends(require_auth)])


# ── Pydantic Schemas ──

class RoleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: Optional[str] = "#3b82f6"
    permissions: Optional[list[str]] = None

class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    permissions: Optional[list[str]] = None
    is_default: Optional[bool] = None

class MemberCreate(BaseModel):
    first_name: str
    last_name: Optional[str] = None
    telegram_id: Optional[int] = None
    telegram_username: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    role_id: Optional[int] = None
    is_admin: bool = False

class MemberUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    telegram_username: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    department: Optional[str] = None
    title: Optional[str] = None
    notes: Optional[str] = None
    role_id: Optional[int] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    avatar_url: Optional[str] = None

class InviteMember(BaseModel):
    telegram_username: str
    role_id: Optional[int] = None


# ── Helper ──

def _user_to_dict(u: User, role: Optional[TeamRole] = None, task_stats: dict = None):
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "telegram_username": u.telegram_username,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "full_name": f"{u.first_name or ''} {u.last_name or ''}".strip() or "Unknown",
        "is_admin": u.is_admin,
        "is_active": u.is_active,
        "phone": u.phone,
        "email": u.email,
        "department": u.department,
        "title": u.title,
        "notes": u.notes,
        "avatar_url": u.avatar_url,
        "role_id": u.role_id,
        "role": role.to_dict() if role else None,
        "timezone": u.timezone,
        "task_stats": task_stats or {},
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def _get_task_stats(db: AsyncSession, user_name: str):
    """Get task stats for a user by their name."""
    if not user_name:
        return {"total": 0, "todo": 0, "active": 0, "done": 0}
    result = await db.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.assignee_name == user_name)
        .group_by(Task.status)
    )
    stats = {"total": 0, "todo": 0, "active": 0, "review": 0, "done": 0}
    for status, count in result.all():
        key = status.value if hasattr(status, 'value') else str(status)
        if key == "in_progress":
            key = "active"
        stats[key] = count
        stats["total"] += count
    return stats


# ═══════════════════════════════════════════
# ROLES CRUD
# ═══════════════════════════════════════════

@router.get("/roles")
async def list_roles(db: AsyncSession = Depends(get_db)):
    """List all team roles with member counts."""
    result = await db.execute(select(TeamRole).order_by(TeamRole.sort_order, TeamRole.id))
    roles = result.scalars().all()

    roles_data = []
    for r in roles:
        cnt = await db.execute(select(func.count(User.id)).where(User.role_id == r.id))
        rd = r.to_dict()
        rd["member_count"] = cnt.scalar() or 0
        roles_data.append(rd)

    return {"roles": roles_data}


@router.post("/roles")
async def create_role(data: RoleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new role."""
    # Check unique name
    existing = await db.execute(select(TeamRole).where(TeamRole.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Role name already exists")

    max_order = await db.execute(select(func.max(TeamRole.sort_order)))
    next_order = (max_order.scalar() or 0) + 1

    role = TeamRole(
        name=data.name,
        description=data.description,
        color=data.color or "#3b82f6",
        permissions=json.dumps(data.permissions) if data.permissions else None,
        sort_order=next_order,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role.to_dict()


@router.patch("/roles/{role_id}")
async def update_role(role_id: int, data: RoleUpdate, db: AsyncSession = Depends(get_db)):
    """Update a role."""
    result = await db.execute(select(TeamRole).where(TeamRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    updates = data.model_dump(exclude_unset=True)
    if "permissions" in updates and updates["permissions"] is not None:
        updates["permissions"] = json.dumps(updates["permissions"])

    # If setting as default, unset other defaults
    if updates.get("is_default"):
        await db.execute(update(TeamRole).values(is_default=False))

    for field, value in updates.items():
        setattr(role, field, value)

    await db.commit()
    await db.refresh(role)
    return role.to_dict()


@router.delete("/roles/{role_id}")
async def delete_role(role_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a role. Members lose their role."""
    result = await db.execute(select(TeamRole).where(TeamRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Unset role for all members with this role
    await db.execute(update(User).where(User.role_id == role_id).values(role_id=None))
    await db.delete(role)
    await db.commit()
    return {"ok": True, "message": f"Role '{role.name}' deleted."}


# ═══════════════════════════════════════════
# MEMBERS CRUD
# ═══════════════════════════════════════════

@router.get("/members")
async def list_members(db: AsyncSession = Depends(get_db)):
    """List all team members with roles and task stats."""
    result = await db.execute(select(User).order_by(User.created_at.asc()))
    users = result.scalars().all()

    # Load all roles
    roles_result = await db.execute(select(TeamRole))
    roles_map = {r.id: r for r in roles_result.scalars().all()}

    members = []
    for u in users:
        role = roles_map.get(u.role_id) if u.role_id else None
        name = u.first_name or u.telegram_username or "Unknown"
        stats = await _get_task_stats(db, name)
        members.append(_user_to_dict(u, role, stats))

    return {"members": members}


@router.get("/members/{member_id}")
async def get_member(member_id: int, db: AsyncSession = Depends(get_db)):
    """Get single member profile."""
    result = await db.execute(select(User).where(User.id == member_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(status_code=404, detail="Member not found")

    role = None
    if u.role_id:
        rr = await db.execute(select(TeamRole).where(TeamRole.id == u.role_id))
        role = rr.scalar_one_or_none()

    name = u.first_name or u.telegram_username or "Unknown"
    stats = await _get_task_stats(db, name)
    return _user_to_dict(u, role, stats)


@router.post("/members")
async def create_member(data: MemberCreate, db: AsyncSession = Depends(get_db)):
    """Manually add a new team member."""
    # Generate a placeholder telegram_id if not provided
    tg_id = data.telegram_id
    if not tg_id:
        # Use a negative ID as placeholder for manually added members
        max_result = await db.execute(select(func.min(User.telegram_id)))
        min_id = max_result.scalar() or 0
        tg_id = min(min_id, 0) - 1

    # Check if telegram_id already exists
    existing = await db.execute(select(User).where(User.telegram_id == tg_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="A member with this Telegram ID already exists")

    user = User(
        telegram_id=tg_id,
        telegram_username=data.telegram_username,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        email=data.email,
        department=data.department,
        title=data.title,
        notes=data.notes,
        role_id=data.role_id,
        is_admin=data.is_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    role = None
    if user.role_id:
        rr = await db.execute(select(TeamRole).where(TeamRole.id == user.role_id))
        role = rr.scalar_one_or_none()

    return _user_to_dict(user, role)


@router.patch("/members/{member_id}")
async def update_member(member_id: int, data: MemberUpdate, db: AsyncSession = Depends(get_db)):
    """Update a team member's profile."""
    result = await db.execute(select(User).where(User.id == member_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)

    await db.commit()
    await db.refresh(user)

    role = None
    if user.role_id:
        rr = await db.execute(select(TeamRole).where(TeamRole.id == user.role_id))
        role = rr.scalar_one_or_none()

    return _user_to_dict(user, role)


@router.delete("/members/{member_id}")
async def delete_member(member_id: int, db: AsyncSession = Depends(get_db)):
    """Remove a team member."""
    result = await db.execute(select(User).where(User.id == member_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Member not found")

    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    await db.delete(user)
    await db.commit()
    return {"ok": True, "message": f"Member '{name}' removed."}


@router.post("/invite")
async def invite_member(data: InviteMember, db: AsyncSession = Depends(get_db)):
    """Invite a member by Telegram username (creates placeholder entry)."""
    username = data.telegram_username.lstrip("@")

    # Check if username already exists
    existing = await db.execute(
        select(User).where(User.telegram_username == username)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"@{username} is already a team member")

    # Create placeholder — will be updated when they message the bot
    max_result = await db.execute(select(func.min(User.telegram_id)))
    min_id = max_result.scalar() or 0
    tg_id = min(min_id, 0) - 1

    user = User(
        telegram_id=tg_id,
        telegram_username=username,
        first_name=username,
        role_id=data.role_id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    role = None
    if user.role_id:
        rr = await db.execute(select(TeamRole).where(TeamRole.id == user.role_id))
        role = rr.scalar_one_or_none()

    return _user_to_dict(user, role)
