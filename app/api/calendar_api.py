"""
Calendar API Routes — OAuth2 callback and calendar REST endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.services.calendar_svc import calendar_service, token_store

calendar_router = APIRouter(prefix="/api/v1/calendar")


# ─── OAuth2 Callback ───

@calendar_router.get("/auth/callback")
async def google_auth_callback(
    code: str,
    state: str = "",
    db: AsyncSession = Depends(get_db),
):
    """
    Google OAuth2 callback handler.
    After user authorizes, Google redirects here with an auth code.
    """
    try:
        credentials = calendar_service.exchange_code(code)
        telegram_id = int(state) if state else 0

        if telegram_id:
            await token_store.save_token(db, telegram_id, credentials)

        # Return a friendly HTML page
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


# ─── Calendar REST API ───

@calendar_router.get("/today/{telegram_id}")
async def get_today(telegram_id: int, db: AsyncSession = Depends(get_db)):
    """Get today's events for a user."""
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    events = await calendar_service.get_today_events(creds)
    return {"events": events}


@calendar_router.get("/week/{telegram_id}")
async def get_week(telegram_id: int, db: AsyncSession = Depends(get_db)):
    """Get this week's events for a user."""
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    events = await calendar_service.get_week_events(creds)
    return {"events": events}


@calendar_router.get("/free/{telegram_id}")
async def get_free_slots(telegram_id: int, db: AsyncSession = Depends(get_db)):
    """Find free time slots today."""
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
async def create_event(telegram_id: int, body: EventCreate, db: AsyncSession = Depends(get_db)):
    """Create a calendar event."""
    creds = await token_store.load_token(db, telegram_id)
    if not creds:
        raise HTTPException(status_code=401, detail="Google Calendar not connected")
    event = await calendar_service.create_event(
        creds,
        title=body.title,
        start_time=body.start_time,
        duration_minutes=body.duration_minutes,
        description=body.description,
        location=body.location,
    )
    return {"event": event}
