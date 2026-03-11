"""
Report API — saved reports with scheduling and export.
"""
import json
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import Optional, List

from app.core.database import get_db
from app.api.auth import require_auth
from app.models.saved_report import SavedReport
from app.services.report_svc import report_service

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.redis_url)

router = APIRouter(prefix="/api/v1", tags=["reports"])


class ReportCreate(BaseModel):
    name: str
    description: Optional[str] = None
    report_type: str = "status_summary"
    filters: Optional[dict] = None
    schedule: str = "none"
    recipients: Optional[List[str]] = None


class ReportUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    report_type: Optional[str] = None
    filters: Optional[dict] = None
    schedule: Optional[str] = None
    recipients: Optional[List[str]] = None
    is_active: Optional[bool] = None


def _report_to_dict(r: SavedReport) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "report_type": r.report_type,
        "filters": json.loads(r.filters_json) if r.filters_json else {},
        "schedule": r.schedule,
        "recipients": json.loads(r.recipients_json) if r.recipients_json else [],
        "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
        "creator_email": r.creator_email,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@limiter.limit("30/minute")
@router.get("/reports")
async def list_reports(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """List all saved reports."""
    result = await db.execute(select(SavedReport).order_by(desc(SavedReport.created_at)))
    reports = list(result.scalars().all())
    return {"reports": [_report_to_dict(r) for r in reports]}


@limiter.limit("15/minute")
@router.post("/reports")
async def create_report(
    request: Request,
    body: ReportCreate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Create a new saved report."""
    report = SavedReport(
        name=body.name,
        description=body.description,
        report_type=body.report_type,
        filters_json=json.dumps(body.filters) if body.filters else None,
        schedule=body.schedule or "none",
        recipients_json=json.dumps(body.recipients) if body.recipients else None,
        creator_email=_auth.get("email", ""),
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    await db.commit()
    return _report_to_dict(report)


@limiter.limit("30/minute")
@router.get("/reports/{report_id}/run")
async def run_report(
    request: Request,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Run a saved report and return the data."""
    result = await db.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    filters = json.loads(report.filters_json) if report.filters_json else {}
    data = await report_service.generate_report(db, report.report_type, filters)

    # Update last_run_at
    report.last_run_at = datetime.now(timezone.utc)
    await db.commit()

    return {"report": _report_to_dict(report), "data": data}


@limiter.limit("30/minute")
@router.get("/reports/{report_id}/export")
async def export_report(
    request: Request,
    report_id: int,
    format: str = "csv",
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Export a report as CSV."""
    result = await db.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    filters = json.loads(report.filters_json) if report.filters_json else {}
    data = await report_service.generate_report(db, report.report_type, filters)

    if format == "csv":
        csv_content = report_service.export_csv(data)
        import io
        return StreamingResponse(
            io.StringIO(csv_content),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{report.name}.csv"'},
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Use 'csv'.")


@limiter.limit("15/minute")
@router.patch("/reports/{report_id}")
async def update_report(
    request: Request,
    report_id: int,
    body: ReportUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Update a saved report."""
    result = await db.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if body.name is not None:
        report.name = body.name
    if body.description is not None:
        report.description = body.description
    if body.report_type is not None:
        report.report_type = body.report_type
    if body.filters is not None:
        report.filters_json = json.dumps(body.filters)
    if body.schedule is not None:
        report.schedule = body.schedule
    if body.recipients is not None:
        report.recipients_json = json.dumps(body.recipients)
    if body.is_active is not None:
        report.is_active = body.is_active

    await db.commit()
    await db.refresh(report)
    return _report_to_dict(report)


@limiter.limit("10/minute")
@router.delete("/reports/{report_id}")
async def delete_report(
    request: Request,
    report_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Delete a saved report."""
    result = await db.execute(select(SavedReport).where(SavedReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await db.delete(report)
    await db.commit()
    return {"ok": True, "deleted": report_id}


@limiter.limit("20/minute")
@router.post("/reports/generate")
async def generate_adhoc_report(
    request: Request,
    body: dict,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Generate an ad-hoc report without saving it."""
    report_type = body.get("report_type", "status_summary")
    filters = body.get("filters", {})
    data = await report_service.generate_report(db, report_type, filters)
    return {"data": data}
