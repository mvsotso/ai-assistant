"""
File API - upload, download, and manage file attachments.
"""
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.api.auth import require_auth
from app.models.task_file import TaskFile
from app.services.file_svc import file_service, UPLOAD_DIR

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.redis_url)

router = APIRouter(prefix="/api/v1", tags=["files"])


def _file_to_dict(f: TaskFile) -> dict:
    return {
        "id": f.id,
        "task_id": f.task_id,
        "filename": f.original_filename,
        "file_size": f.file_size,
        "mime_type": f.mime_type,
        "uploader_email": f.uploader_email,
        "description": f.description,
        "ai_summary": f.ai_summary,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


@limiter.limit("10/minute")
@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    task_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Upload a file (max 25MB)."""
    file_bytes = await file.read()
    if len(file_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 25MB.")

    task_file = await file_service.save_file(
        db, file_bytes, file.filename or "unnamed",
        mime_type=file.content_type, task_id=task_id,
        uploader_email=_auth.get("email", ""), description=description,
    )
    await db.commit()
    return _file_to_dict(task_file)


@limiter.limit("30/minute")
@router.get("/files")
async def list_files(
    request: Request,
    task_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """List files, optionally filtered by task_id."""
    if task_id:
        files = await file_service.get_files_for_task(db, task_id)
    else:
        files = await file_service.get_all_files(db)
    return {"files": [_file_to_dict(f) for f in files]}


@limiter.limit("30/minute")
@router.get("/files/{file_id}")
async def get_file_meta(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get file metadata."""
    task_file, _ = await file_service.get_file(db, file_id)
    if not task_file:
        raise HTTPException(status_code=404, detail="File not found")
    return _file_to_dict(task_file)


@limiter.limit("20/minute")
@router.get("/files/{file_id}/download")
async def download_file(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Download a file."""
    task_file, full_path = await file_service.get_file(db, file_id)
    if not task_file or not full_path or not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        full_path,
        filename=task_file.original_filename,
        media_type=task_file.mime_type or "application/octet-stream",
    )


@limiter.limit("5/minute")
@router.post("/files/{file_id}/analyze")
async def analyze_file(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """AI-analyze a file."""
    summary = await file_service.analyze_file(db, file_id)
    await db.commit()
    return {"file_id": file_id, "ai_summary": summary}


@limiter.limit("10/minute")
@router.delete("/files/{file_id}")
async def delete_file(
    request: Request,
    file_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Delete a file."""
    success = await file_service.delete_file(db, file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    await db.commit()
    return {"ok": True, "deleted": file_id}


@limiter.limit("10/minute")
@router.post("/tasks/{task_id}/files")
async def upload_task_file(
    request: Request,
    task_id: int,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Upload a file linked to a task."""
    file_bytes = await file.read()
    if len(file_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Max 25MB.")

    task_file = await file_service.save_file(
        db, file_bytes, file.filename or "unnamed",
        mime_type=file.content_type, task_id=task_id,
        uploader_email=_auth.get("email", ""), description=description,
    )
    await db.commit()
    return _file_to_dict(task_file)
