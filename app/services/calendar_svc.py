"""
Google Calendar Service — OAuth2 integration with read/write operations.
Includes Google Drive file upload for event attachments.
"""
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone, time
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings
from app.models.user import User

settings = get_settings()
logger = logging.getLogger(__name__)

# OAuth2 scopes — includes Drive for file attachments
SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/drive.file",
]

DEFAULT_TZ = "Asia/Phnom_Penh"

# MIME type mapping
MIME_MAP = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".mp4": "video/mp4",
    ".mp3": "audio/mpeg",
}


class CalendarTokenStore:
    """Stores and retrieves Google OAuth2 tokens from the user record."""

    @staticmethod
    async def save_token(db: AsyncSession, telegram_id: int, credentials: Credentials):
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            token_data = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": list(credentials.scopes or SCOPES),
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
            }
            user.google_token = json.dumps(token_data)
            await db.flush()

    @staticmethod
    async def load_token(db: AsyncSession, telegram_id: int) -> Optional[Credentials]:
        result = await db.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user or not getattr(user, "google_token", None):
            return None
        try:
            token_data = json.loads(user.google_token)
            creds = Credentials(
                token=token_data["token"],
                refresh_token=token_data.get("refresh_token"),
                token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=token_data.get("client_id", settings.google_client_id),
                client_secret=token_data.get("client_secret", settings.google_client_secret),
                scopes=token_data.get("scopes", SCOPES),
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                await CalendarTokenStore.save_token(db, telegram_id, creds)
            return creds
        except Exception as e:
            logger.error(f"Failed to load Google token for {telegram_id}: {e}")
            return None


class GoogleCalendarService:
    """Google Calendar + Drive API wrapper."""

    def __init__(self):
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri

    # ─── OAuth2 Flow ───

    def get_auth_url(self, state: str = "") -> str:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )
        return auth_url

    def exchange_code(self, code: str) -> Credentials:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [self.redirect_uri],
                }
            },
            scopes=SCOPES,
        )
        flow.redirect_uri = self.redirect_uri
        # Accept additional scopes Google returns (userinfo, openid, etc.)
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        flow.fetch_token(code=code)
        return flow.credentials

    def _build_service(self, credentials: Credentials):
        return build("calendar", "v3", credentials=credentials)

    def _build_drive_service(self, credentials: Credentials):
        return build("drive", "v3", credentials=credentials)

    # ─── Google Drive: Upload File ───

    async def upload_to_drive(
        self,
        credentials: Credentials,
        file_path: str,
        filename: str,
        mime_type: str = None,
    ) -> dict:
        """
        Upload a file to Google Drive and return file metadata.
        Returns: {"id": "...", "name": "...", "webViewLink": "...", "mimeType": "..."}
        """
        drive = self._build_drive_service(credentials)

        if not mime_type:
            ext = os.path.splitext(filename)[1].lower()
            mime_type = MIME_MAP.get(ext, "application/octet-stream")

        file_metadata = {
            "name": filename,
            "parents": [],  # Root of Drive
        }

        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

        file = drive.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, name, webViewLink, webContentLink, mimeType, size",
            supportsAllDrives=True,
        ).execute()

        # Make file accessible via link
        try:
            drive.permissions().create(
                fileId=file["id"],
                body={"type": "anyone", "role": "reader"},
            ).execute()
        except Exception as e:
            logger.warning(f"Could not set file permissions: {e}")

        logger.info(f"Uploaded to Drive: {file.get('name')} ({file.get('id')})")
        return {
            "id": file.get("id"),
            "name": file.get("name"),
            "webViewLink": file.get("webViewLink"),
            "webContentLink": file.get("webContentLink"),
            "mimeType": file.get("mimeType"),
            "size": file.get("size"),
        }

    # ─── Read Operations ───

    async def get_today_events(self, credentials: Credentials, tz: str = DEFAULT_TZ) -> list[dict]:
        service = self._build_service(credentials)
        now = datetime.now(timezone.utc)
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        events_result = service.events().list(
            calendarId="primary", timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(), singleEvents=True,
            orderBy="startTime", timeZone=tz,
        ).execute()
        return [self._format_event(e, tz) for e in events_result.get("items", [])]

    async def get_week_events(self, credentials: Credentials, tz: str = DEFAULT_TZ) -> list[dict]:
        service = self._build_service(credentials)
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=7)
        events_result = service.events().list(
            calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime", timeZone=tz, maxResults=50,
        ).execute()
        return [self._format_event(e, tz) for e in events_result.get("items", [])]

    async def get_upcoming_events(self, credentials: Credentials, hours: int = 2, tz: str = DEFAULT_TZ) -> list[dict]:
        service = self._build_service(credentials)
        now = datetime.now(timezone.utc)
        end = now + timedelta(hours=hours)
        events_result = service.events().list(
            calendarId="primary", timeMin=now.isoformat(), timeMax=end.isoformat(),
            singleEvents=True, orderBy="startTime", timeZone=tz,
        ).execute()
        return [self._format_event(e, tz) for e in events_result.get("items", [])]

    # ─── Free Slot Detection ───

    async def find_free_slots(
        self, credentials: Credentials, date: datetime = None,
        work_start: int = 8, work_end: int = 18,
        min_duration_minutes: int = 30, tz: str = DEFAULT_TZ,
    ) -> list[dict]:
        if date is None:
            date = datetime.now(timezone.utc)
        service = self._build_service(credentials)
        start_of_day = date.replace(hour=work_start, minute=0, second=0, microsecond=0)
        end_of_day = date.replace(hour=work_end, minute=0, second=0, microsecond=0)
        events_result = service.events().list(
            calendarId="primary", timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(), singleEvents=True,
            orderBy="startTime", timeZone=tz,
        ).execute()
        busy_periods = []
        for e in events_result.get("items", []):
            start = e["start"].get("dateTime", e["start"].get("date"))
            end = e["end"].get("dateTime", e["end"].get("date"))
            if start and end:
                busy_periods.append({"start": datetime.fromisoformat(start), "end": datetime.fromisoformat(end)})
        free_slots = []
        current = start_of_day
        for period in sorted(busy_periods, key=lambda x: x["start"]):
            if period["start"] > current:
                gap = (period["start"] - current).total_seconds() / 60
                if gap >= min_duration_minutes:
                    free_slots.append({"start": current.strftime("%I:%M %p"), "end": period["start"].strftime("%I:%M %p"), "duration_minutes": int(gap)})
            current = max(current, period["end"])
        if current < end_of_day:
            gap = (end_of_day - current).total_seconds() / 60
            if gap >= min_duration_minutes:
                free_slots.append({"start": current.strftime("%I:%M %p"), "end": end_of_day.strftime("%I:%M %p"), "duration_minutes": int(gap)})
        return free_slots

    # ─── Write Operations ───

    async def create_event(
        self, credentials: Credentials, title: str, start_time: datetime,
        end_time: datetime = None, duration_minutes: int = 60,
        description: str = None, location: str = None,
        attendees: list[str] = None, attachments: list[dict] = None,
        tz: str = DEFAULT_TZ,
    ) -> dict:
        service = self._build_service(credentials)
        if end_time is None:
            end_time = start_time + timedelta(minutes=duration_minutes)
        event_body = {
            "summary": title,
            "start": {"dateTime": start_time.isoformat(), "timeZone": tz},
            "end": {"dateTime": end_time.isoformat(), "timeZone": tz},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 5}]},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": e} for e in attendees]
        if attachments:
            event_body["attachments"] = [
                {"fileUrl": a["webViewLink"], "mimeType": a.get("mimeType", "application/octet-stream"), "title": a["name"]}
                for a in attachments
            ]

        event = service.events().insert(
            calendarId="primary",
            body=event_body,
            supportsAttachments=True,
        ).execute()
        return self._format_event(event, tz)

    async def create_event_from_task(
        self, credentials: Credentials, task_title: str, due_date: datetime,
        duration_minutes: int = 60, tz: str = DEFAULT_TZ,
    ) -> dict:
        return await self.create_event(
            credentials=credentials, title=f"📋 {task_title}",
            start_time=due_date - timedelta(minutes=duration_minutes),
            duration_minutes=duration_minutes,
            description=f"Task deadline: {task_title}\nCreated by AI Assistant", tz=tz,
        )

    async def update_event(
        self, credentials: Credentials, event_id: str,
        title: str = None, start_time: datetime = None, end_time: datetime = None,
        description: str = None, location: str = None,
        attachments: list[dict] = None, tz: str = DEFAULT_TZ,
    ) -> dict:
        service = self._build_service(credentials)
        event = service.events().get(calendarId="primary", eventId=event_id).execute()
        if title:
            event["summary"] = title
        if start_time:
            event["start"] = {"dateTime": start_time.isoformat(), "timeZone": tz}
        if end_time:
            event["end"] = {"dateTime": end_time.isoformat(), "timeZone": tz}
        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location
        if attachments:
            existing = event.get("attachments", [])
            new_attachments = [
                {"fileUrl": a["webViewLink"], "mimeType": a.get("mimeType", "application/octet-stream"), "title": a["name"]}
                for a in attachments
            ]
            event["attachments"] = existing + new_attachments

        updated = service.events().update(
            calendarId="primary", eventId=event_id, body=event,
            supportsAttachments=True,
        ).execute()
        return self._format_event(updated, tz)

    async def delete_event(self, credentials: Credentials, event_id: str) -> bool:
        service = self._build_service(credentials)
        try:
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to delete event {event_id}: {e}")
            return False

    async def check_conflicts(
        self, credentials: Credentials, start_time: datetime, end_time: datetime, tz: str = DEFAULT_TZ,
    ) -> list[dict]:
        service = self._build_service(credentials)
        events_result = service.events().list(
            calendarId="primary", timeMin=start_time.isoformat(), timeMax=end_time.isoformat(),
            singleEvents=True, orderBy="startTime", timeZone=tz,
        ).execute()
        return [self._format_event(e, tz) for e in events_result.get("items", [])]

    # ─── Helpers ───

    def _format_event(self, event: dict, tz: str = DEFAULT_TZ) -> dict:
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        end = event["end"].get("dateTime", event["end"].get("date", ""))
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)
            duration_min = int((end_dt - start_dt).total_seconds() / 60)
            start_str = start_dt.strftime("%I:%M %p")
            end_str = end_dt.strftime("%I:%M %p")
            duration_str = f"{duration_min // 60}h {duration_min % 60}m" if duration_min >= 60 else f"{duration_min}m"
        except (ValueError, TypeError):
            start_str, end_str, duration_str, duration_min = start, end, "", 0

        # Extract attachments
        attachments = []
        for a in event.get("attachments", []):
            attachments.append({
                "title": a.get("title", "Attachment"),
                "fileUrl": a.get("fileUrl"),
                "mimeType": a.get("mimeType"),
                "iconLink": a.get("iconLink"),
            })

        return {
            "id": event.get("id"),
            "title": event.get("summary", "(No title)"),
            "start": start_str, "end": end_str,
            "start_raw": start, "end_raw": end,
            "duration": duration_str, "duration_minutes": duration_min,
            "location": event.get("location"),
            "description": event.get("description"),
            "status": event.get("status"),
            "link": event.get("htmlLink"),
            "attachments": attachments,
        }


# Singleton
calendar_service = GoogleCalendarService()
token_store = CalendarTokenStore()
