"""
Category & Subcategory API
Full CRUD for task categories and subcategories
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.category import Category, Subcategory
from app.models.task import Task
from app.api.auth import require_auth
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/v1/categories", tags=["categories"], dependencies=[Depends(require_auth)])


# ── Pydantic Schemas ──

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class SubcategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category_id: int

class SubcategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ── Category CRUD ──

@router.get("")
async def list_categories(db: AsyncSession = Depends(get_db)):
    """List all categories with subcategories and task counts."""
    result = await db.execute(
        select(Category)
        .options(selectinload(Category.subcategories))
        .order_by(Category.sort_order, Category.id)
    )
    cats = result.scalars().all()

    cats_data = []
    for c in cats:
        cd = c.to_dict()
        count_result = await db.execute(
            select(func.count(Task.id)).where(Task.category == c.name)
        )
        cd["task_count"] = count_result.scalar() or 0

        for sc in cd["subcategories"]:
            sc_obj = next((s for s in c.subcategories if s.id == sc["id"]), None)
            if sc_obj:
                sc_count = await db.execute(
                    select(func.count(Task.id)).where(
                        Task.category == c.name,
                        Task.subcategory == sc_obj.name
                    )
                )
                sc["task_count"] = sc_count.scalar() or 0

        cats_data.append(cd)

    uncategorized = await db.execute(
        select(func.count(Task.id)).where(Task.category.is_(None))
    )
    uncategorized_count = uncategorized.scalar() or 0

    return {
        "categories": cats_data,
        "uncategorized_count": uncategorized_count
    }


@router.post("")
async def create_category(data: CategoryCreate, db: AsyncSession = Depends(get_db)):
    """Create a new category."""
    existing = await db.execute(select(Category).where(Category.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Category with this name already exists")

    max_order = await db.execute(select(func.max(Category.sort_order)))
    next_order = (max_order.scalar() or 0) + 1

    cat = Category(
        name=data.name,
        description=data.description,
        icon=data.icon or "📂",
        color=data.color or "#3b82f6",
        sort_order=next_order,
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat.to_dict()


@router.patch("/{cat_id}")
async def update_category(cat_id: int, data: CategoryUpdate, db: AsyncSession = Depends(get_db)):
    """Update a category."""
    result = await db.execute(
        select(Category).options(selectinload(Category.subcategories)).where(Category.id == cat_id)
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    old_name = cat.name
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cat, field, value)

    # If name changed, update tasks with old category name
    if data.name and data.name != old_name:
        await db.execute(
            update(Task).where(Task.category == old_name).values(category=data.name)
        )

    await db.commit()
    await db.refresh(cat)
    return cat.to_dict()


@router.delete("/{cat_id}")
async def delete_category(cat_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a category. Tasks lose their category."""
    result = await db.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    # Clear category from tasks
    await db.execute(
        update(Task).where(Task.category == cat.name).values(category=None, subcategory=None)
    )

    await db.delete(cat)
    await db.commit()
    return {"ok": True, "message": f"Category \'{cat.name}\' deleted."}


# ── Subcategory CRUD ──

@router.post("/subcategories")
async def create_subcategory(data: SubcategoryCreate, db: AsyncSession = Depends(get_db)):
    """Create a subcategory under a category."""
    parent = await db.execute(select(Category).where(Category.id == data.category_id))
    if not parent.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Parent category not found")

    max_order = await db.execute(
        select(func.max(Subcategory.sort_order)).where(Subcategory.category_id == data.category_id)
    )
    next_order = (max_order.scalar() or 0) + 1

    sc = Subcategory(
        name=data.name,
        description=data.description,
        category_id=data.category_id,
        sort_order=next_order,
    )
    db.add(sc)
    await db.commit()
    await db.refresh(sc)
    return sc.to_dict()


@router.patch("/subcategories/{sc_id}")
async def update_subcategory(sc_id: int, data: SubcategoryUpdate, db: AsyncSession = Depends(get_db)):
    """Update a subcategory."""
    result = await db.execute(select(Subcategory).where(Subcategory.id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    old_name = sc.name
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(sc, field, value)

    # If name changed, update tasks
    if data.name and data.name != old_name:
        parent = await db.execute(select(Category).where(Category.id == sc.category_id))
        cat = parent.scalar_one_or_none()
        if cat:
            await db.execute(
                update(Task).where(Task.category == cat.name, Task.subcategory == old_name)
                .values(subcategory=data.name)
            )

    await db.commit()
    await db.refresh(sc)
    return sc.to_dict()


@router.delete("/subcategories/{sc_id}")
async def delete_subcategory(sc_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a subcategory. Tasks keep category but lose subcategory."""
    result = await db.execute(select(Subcategory).where(Subcategory.id == sc_id))
    sc = result.scalar_one_or_none()
    if not sc:
        raise HTTPException(status_code=404, detail="Subcategory not found")

    parent = await db.execute(select(Category).where(Category.id == sc.category_id))
    cat = parent.scalar_one_or_none()
    if cat:
        await db.execute(
            update(Task).where(Task.category == cat.name, Task.subcategory == sc.name)
            .values(subcategory=None)
        )

    await db.delete(sc)
    await db.commit()
    return {"ok": True, "message": f"Subcategory \'{sc.name}\' deleted."}
