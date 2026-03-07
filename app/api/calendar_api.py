"""
Calendar API Routes — OAuth2 callback, calendar REST, file attachments.
Supports both Telegram bot (by telegram_id) and web dashboard (by session token).
"""
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.config import get_settings
from app.services.calendar_svc import calendar_service, token_store
from app.api.auth import verify_session_token

settings = get_settings()
calendar_router = APIRouter(prefix="/api/v1/calendar")


# ─── Helper: Get credentials from web session ───

async def get_web_credentials(request: Request, db: AsyncSession):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_session_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    telegram_id = int(settings.admin_telegram_id)
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected. Use /connect in Telegram first.")
    return creds


# ─── OAuth2 Callback ───

@calendar_router.get("/auth/callback")
async def google_auth_callback(code: str, state: str = "", db: AsyncSession = Depends(get_db)):
    try:
        credentials = calendar_service.exchange_code(code)
        telegram_id = int(state) if state else 0
        if telegram_id:
            await token_store.save_token(db, telegram_id, credentials)
        return HTMLResponse(content="""
        <!DOCTYPE html><html><head><title>Calendar Connected!</title>
        <style>body{font-family:-apple-system,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#0b0c10;color:#e6e8f0;margin:0}.card{text-align:center;background:#181a24;padding:48px;border-radius:20px;border:1px solid #252838;max-width:400px}.icon{font-size:48px;margin-bottom:16px}h1{font-size:24px;margin:0 0 8px}p{color:#6b7094;font-size:14px}</style></head>
        <body><div class="card"><div class="icon">✅</div><h1>Calendar Connected!</h1><p>Google Calendar + Drive linked to AI Assistant.<br>You can close this window.</p></div></body></html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")


# ─── Telegram Bot Endpoints ───

@calendar_router.get("/today/{telegram_id}")
async def get_today(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    return {"events": await calendar_service.get_today_events(creds)}

@calendar_router.get("/week/{telegram_id}")
async def get_week(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    return {"events": await calendar_service.get_week_events(creds)}

@calendar_router.get("/free/{telegram_id}")
async def get_free_slots(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    return {"free_slots": await calendar_service.find_free_slots(creds)}

class EventCreate(BaseModel):
    title: str
    start_time: datetime
    duration_minutes: int = 60
    description: Optional[str] = None
    location: Optional[str] = None

@calendar_router.post("/events/{telegram_id}")
async def create_event_bot(telegram_id: int, body: EventCreate, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    event = await calendar_service.create_event(
        creds, title=body.title, start_time=body.start_time,
        duration_minutes=body.duration_minutes, description=body.description, location=body.location,
    )
    return {"event": event}


# ═══════════════════════════════════════════════════════════
# ─── Web Dashboard Endpoints (session auth) ───
# ═══════════════════════════════════════════════════════════

class WebEventCreate(BaseModel):
    title: str
    start_time: str
    end_time: Optional[str] = None
    duration_minutes: int = 60
    description: Optional[str] = None
    location: Optional[str] = None

class WebEventUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


@calendar_router.get("/events")
async def list_events_web(request: Request, start: str = None, end: str = None, db: AsyncSession = Depends(get_db)):
    creds = await get_web_credentials(request, db)
    from datetime import timezone as tz_mod
    now = datetime.now(tz_mod.utc)
    if start:
        try:
            time_min = datetime.fromisoformat(start.replace('Z', '+00:00'))
        except ValueError:
            time_min = datetime.fromisoformat(start + "T00:00:00+00:00")
    else:
        time_min = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if end:
        try:
            time_max = datetime.fromisoformat(end.replace('Z', '+00:00'))
        except ValueError:
            time_max = datetime.fromisoformat(end + "T23:59:59+00:00")
    else:
        time_max = time_min.replace(month=time_min.month + 1) if time_min.month < 12 else time_min.replace(year=time_min.year + 1, month=1)
    # Ensure timezone-aware for Google API
    if time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=tz_mod.utc)
    if time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=tz_mod.utc)
    service = calendar_service._build_service(creds)
    events_result = service.events().list(
        calendarId="primary", timeMin=time_min.isoformat(), timeMax=time_max.isoformat(),
        singleEvents=True, orderBy="startTime", timeZone="Asia/Phnom_Penh", maxResults=250,
    ).execute()
    formatted = [calendar_service._format_event(e, "Asia/Phnom_Penh") for e in events_result.get("items", [])]
    return {"events": formatted, "count": len(formatted)}


@calendar_router.post("/events")
async def create_event_web(body: WebEventCreate, request: Request, db: AsyncSession = Depends(get_db)):
    creds = await get_web_credentials(request, db)
    start_time = datetime.fromisoformat(body.start_time.replace('Z', '+00:00'))
    end_time = datetime.fromisoformat(body.end_time.replace('Z', '+00:00')) if body.end_time else None
    event = await calendar_service.create_event(
        creds, title=body.title, start_time=start_time, end_time=end_time,
        duration_minutes=body.duration_minutes, description=body.description, location=body.location,
    )
    return {"event": event}


@calendar_router.put("/events/{event_id}")
async def update_event_web(event_id: str, body: WebEventUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    creds = await get_web_credentials(request, db)
    start_time = datetime.fromisoformat(body.start_time.replace('Z', '+00:00')) if body.start_time else None
    end_time = datetime.fromisoformat(body.end_time.replace('Z', '+00:00')) if body.end_time else None
    service = calendar_service._build_service(creds)
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    if body.title is not None:
        event["summary"] = body.title
    if body.description is not None:
        event["description"] = body.description
    if body.location is not None:
        event["location"] = body.location
    if start_time:
        event["start"] = {"dateTime": start_time.isoformat(), "timeZone": "Asia/Phnom_Penh"}
    if end_time:
        event["end"] = {"dateTime": end_time.isoformat(), "timeZone": "Asia/Phnom_Penh"}
    updated = service.events().update(calendarId="primary", eventId=event_id, body=event, supportsAttachments=True).execute()
    return {"event": calendar_service._format_event(updated, "Asia/Phnom_Penh")}


@calendar_router.delete("/events/{event_id}")
async def delete_event_web(event_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    creds = await get_web_credentials(request, db)
    success = await calendar_service.delete_event(creds, event_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete event")
    return {"deleted": True, "event_id": event_id}


# ─── File Upload to Drive + Attach to Event ───

@calendar_router.post("/events/{event_id}/attach")
async def attach_file_to_event(
    event_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file to Google Drive and attach it to a calendar event."""
    creds = await get_web_credentials(request, db)

    # Save uploaded file temporarily
    suffix = os.path.splitext(file.filename)[1] if file.filename else ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Upload to Google Drive
        drive_file = await calendar_service.upload_to_drive(
            creds, tmp_path, file.filename, file.content_type
        )

        # Attach to calendar event
        service = calendar_service._build_service(creds)
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        existing_attachments = event.get("attachments", [])
        existing_attachments.append({
            "fileUrl": drive_file["webViewLink"],
            "mimeType": drive_file.get("mimeType", "application/octet-stream"),
            "title": drive_file["name"],
        })
        event["attachments"] = existing_attachments
        updated = service.events().update(
            calendarId="primary", eventId=event_id, body=event,
            supportsAttachments=True,
        ).execute()

        return {
            "event": calendar_service._format_event(updated, "Asia/Phnom_Penh"),
            "uploaded_file": drive_file,
        }
    finally:
        os.unlink(tmp_path)


@calendar_router.post("/events/create-with-file")
async def create_event_with_file(
    request: Request,
    title: str = Form(...),
    start_time: str = Form(...),
    end_time: str = Form(None),
    description: str = Form(None),
    location: str = Form(None),
    file: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Create a calendar event with an optional file attachment (uploaded to Drive)."""
    creds = await get_web_credentials(request, db)

    st = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    et = datetime.fromisoformat(end_time.replace('Z', '+00:00')) if end_time else None

    attachments = None
    if file and file.filename:
        suffix = os.path.splitext(file.filename)[1] if file.filename else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            drive_file = await calendar_service.upload_to_drive(
                creds, tmp_path, file.filename, file.content_type
            )
            attachments = [drive_file]
        finally:
            os.unlink(tmp_path)

    event = await calendar_service.create_event(
        creds, title=title, start_time=st, end_time=et,
        description=description, location=location, attachments=attachments,
    )
    return {"event": event}
