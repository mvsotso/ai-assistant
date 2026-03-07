"""
Calendar API Routes — OAuth2 callback and calendar REST endpoints.
Supports both Telegram bot (by telegram_id) and web dashboard (by session token).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
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
    """Extract credentials from web session token → admin telegram_id."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth[7:]
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    # Map web user to admin telegram_id for calendar access
    telegram_id = settings.admin_telegram_id
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected. Use /connect in Telegram first.")
    return creds


# ─── OAuth2 Callback ───

@calendar_router.get("/auth/callback")
async def google_auth_callback(
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """Google OAuth2 callback handler."""
    try:
        credentials = calendar_service.exchange_code(code)
        telegram_id = int(state) if state else 0
        if telegram_id:
            await token_store.save_token(db, telegram_id, credentials)
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>Calendar Connected!</title>
        <style>
            body { font-family: -apple-system, sans-serif; display: flex; 
                   justify-content: center; align-items: center; height: 100vh;
                   background: #0b0c10; color: #e6e8f0; margin: 0; }
            .card { text-align: center; background: #181a24; padding: 48px;
                    border-radius: 20px; border: 1px solid #252838; max-width: 400px; }
            .icon { font-size: 48px; margin-bottom: 16px; }
            h1 { font-size: 24px; margin: 0 0 8px; }
            p { color: #6b7094; font-size: 14px; }
        </style></head>
        <body>
            <div class="card">
                <div class="icon">✅</div>
                <h1>Calendar Connected!</h1>
                <p>Your Google Calendar is now linked to your AI Assistant.<br>
                You can close this window and return to Telegram.</p>
            </div>
        </body>
        </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authorization failed: {str(e)}")


# ─── Telegram Bot Endpoints (by telegram_id) ───

@calendar_router.get("/today/{telegram_id}")
async def get_today(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    events = await calendar_service.get_today_events(creds)
    return {"events": events}


@calendar_router.get("/week/{telegram_id}")
async def get_week(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    events = await calendar_service.get_week_events(creds)
    return {"events": events}


@calendar_router.get("/free/{telegram_id}")
async def get_free_slots(telegram_id: int, db: AsyncSession = Depends(get_db)):
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    slots = await calendar_service.find_free_slots(creds)
    return {"free_slots": slots}


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
# ─── Web Dashboard Calendar Endpoints (session auth) ───
# ═══════════════════════════════════════════════════════════

class WebEventCreate(BaseModel):
    title: str
    start_time: str  # ISO datetime string
    end_time: Optional[str] = None  # ISO datetime string
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
async def list_events_web(
    request: Request,
    start: str = None,
    end: str = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List calendar events for a date range.
    Query params: start (ISO date), end (ISO date).
    Defaults to current month if not specified.
    """
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
        # End of month
        if time_min.month == 12:
            time_max = time_min.replace(year=time_min.year + 1, month=1)
        else:
            time_max = time_min.replace(month=time_min.month + 1)

    service = calendar_service._build_service(creds)
    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min.isoformat(),
        timeMax=time_max.isoformat(),
        singleEvents=True,
        orderBy="startTime",
        timeZone="Asia/Phnom_Penh",
        maxResults=250,
    ).execute()

    events = events_result.get("items", [])
    formatted = [calendar_service._format_event(e, "Asia/Phnom_Penh") for e in events]
    return {"events": formatted, "count": len(formatted)}


@calendar_router.post("/events")
async def create_event_web(
    body: WebEventCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new calendar event from the web dashboard."""
    creds = await get_web_credentials(request, db)

    start_time = datetime.fromisoformat(body.start_time.replace('Z', '+00:00'))
    end_time = None
    if body.end_time:
        end_time = datetime.fromisoformat(body.end_time.replace('Z', '+00:00'))

    event = await calendar_service.create_event(
        creds,
        title=body.title,
        start_time=start_time,
        end_time=end_time,
        duration_minutes=body.duration_minutes,
        description=body.description,
        location=body.location,
    )
    return {"event": event}


@calendar_router.put("/events/{event_id}")
async def update_event_web(
    event_id: str,
    body: WebEventUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing calendar event from the web dashboard."""
    creds = await get_web_credentials(request, db)

    start_time = None
    end_time = None
    if body.start_time:
        start_time = datetime.fromisoformat(body.start_time.replace('Z', '+00:00'))
    if body.end_time:
        end_time = datetime.fromisoformat(body.end_time.replace('Z', '+00:00'))

    # Use extended update that also handles description/location
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

    updated = service.events().update(
        calendarId="primary", eventId=event_id, body=event
    ).execute()
    return {"event": calendar_service._format_event(updated, "Asia/Phnom_Penh")}


@calendar_router.delete("/events/{event_id}")
async def delete_event_web(
    event_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a calendar event from the web dashboard."""
    creds = await get_web_credentials(request, db)
    success = await calendar_service.delete_event(creds, event_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete event")
    return {"deleted": True, "event_id": event_id}
