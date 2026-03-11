"""
File Service - manages file upload, storage, and AI analysis.
"""
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task_file import TaskFile

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


def _ensure_upload_dir():
    """Ensure upload directory exists."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def _get_storage_path(original_filename: str) -> tuple:
    """Generate storage path: /uploads/YYYY/MM/uuid_filename"""
    now = datetime.utcnow()
    year_dir = os.path.join(UPLOAD_DIR, str(now.year))
    month_dir = os.path.join(year_dir, f"{now.month:02d}")
    os.makedirs(month_dir, exist_ok=True)

    file_uuid = uuid.uuid4().hex[:12]
    safe_name = original_filename.replace(" ", "_").replace("/", "_")
    stored_name = f"{file_uuid}_{safe_name}"
    full_path = os.path.join(month_dir, stored_name)
    rel_path = os.path.join(str(now.year), f"{now.month:02d}", stored_name)
    return full_path, rel_path, stored_name


class FileService:

    async def save_file(self, db: AsyncSession, file_bytes: bytes, original_filename: str,
                        mime_type: str = None, task_id: int = None, uploader_email: str = None,
                        description: str = None) -> TaskFile:
        """Save uploaded file to disk and create DB record."""
        _ensure_upload_dir()

        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB")

        full_path, rel_path, stored_name = _get_storage_path(original_filename)

        # Write file to disk
        with open(full_path, 'wb') as f:
            f.write(file_bytes)

        # Create DB record
        task_file = TaskFile(
            task_id=task_id,
            filename=stored_name,
            original_filename=original_filename,
            file_size=len(file_bytes),
            mime_type=mime_type,
            storage_path=rel_path,
            uploader_email=uploader_email,
            description=description,
        )
        db.add(task_file)
        await db.flush()
        await db.refresh(task_file)
        return task_file

    async def get_file(self, db: AsyncSession, file_id: int) -> tuple:
        """Get file metadata and full path."""
        result = await db.execute(select(TaskFile).where(TaskFile.id == file_id))
        task_file = result.scalar_one_or_none()
        if not task_file:
            return None, None
        full_path = os.path.join(UPLOAD_DIR, task_file.storage_path)
        return task_file, full_path

    async def get_files_for_task(self, db: AsyncSession, task_id: int) -> list:
        """Get all files for a task."""
        result = await db.execute(
            select(TaskFile).where(TaskFile.task_id == task_id).order_by(TaskFile.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_all_files(self, db: AsyncSession, limit: int = 50) -> list:
        """Get all files."""
        result = await db.execute(
            select(TaskFile).order_by(TaskFile.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_file(self, db: AsyncSession, file_id: int) -> bool:
        """Delete file from disk and DB."""
        task_file, full_path = await self.get_file(db, file_id)
        if not task_file:
            return False

        # Remove from disk
        if full_path and os.path.exists(full_path):
            try:
                os.remove(full_path)
            except OSError as e:
                logger.warning(f"Failed to delete file from disk: {e}")

        await db.delete(task_file)
        return True

    async def analyze_file(self, db: AsyncSession, file_id: int) -> str:
        """Use AI to analyze file contents."""
        task_file, full_path = await self.get_file(db, file_id)
        if not task_file or not full_path or not os.path.exists(full_path):
            return "File not found"

        try:
            # Read file
            with open(full_path, 'rb') as f:
                file_bytes = f.read()

            # Use existing file processor
            from app.services.file_processor import extract_text_from_file
            extracted = await extract_text_from_file(file_bytes, task_file.original_filename)

            if extracted.get("type") == "text" and extracted.get("content"):
                # Use AI to summarize
                from app.services.ai_engine import ai_engine
                summary = await ai_engine.analyze_content(
                    extracted["content"][:5000],
                    f"Summarize this {task_file.original_filename} file content in 3-5 bullet points:"
                )
                task_file.ai_summary = summary
                return summary
            elif extracted.get("type") == "image":
                task_file.ai_summary = "Image file - visual analysis not available in text mode"
                return task_file.ai_summary
            else:
                task_file.ai_summary = "Could not extract text from this file"
                return task_file.ai_summary
        except Exception as e:
            logger.error(f"File analysis failed: {e}")
            return f"Analysis failed: {str(e)}"


file_service = FileService()
