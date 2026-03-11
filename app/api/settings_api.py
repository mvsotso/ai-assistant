"""
Settings API — admin-configurable system settings (SMTP, etc.).
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.system_setting import SystemSetting
from app.api.auth import require_auth, require_permission

logger = logging.getLogger(__name__)

settings_router = APIRouter(
    prefix="/api/v1/settings",
    tags=["Settings"],
    dependencies=[Depends(require_permission("admin"))],
)

# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings as _gs
_limiter = Limiter(key_func=get_remote_address, storage_uri=_gs().redis_url)

# SMTP setting keys and their properties
SMTP_KEYS = {
    "smtp_host": {"default": "", "secret": False},
    "smtp_port": {"default": "587", "secret": False},
    "smtp_username": {"default": "", "secret": False},
    "smtp_password": {"default": "", "secret": True},
    "smtp_from_email": {"default": "", "secret": False},
    "smtp_from_name": {"default": "AI Assistant", "secret": False},
    "smtp_use_tls": {"default": "true", "secret": False},
}


class SmtpSettingsRequest(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: Optional[str] = None  # None means "don't change"
    smtp_from_email: str = ""
    smtp_from_name: str = "AI Assistant"
    smtp_use_tls: bool = True


class TestEmailRequest(BaseModel):
    to_email: str


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    """Get a setting value from database."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def get_settings_dict(db: AsyncSession, keys: list, unmask: bool = False) -> dict:
    """Get multiple settings as a dictionary."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key.in_(keys))
    )
    settings = {s.key: s for s in result.scalars().all()}
    out = {}
    for key in keys:
        if key in settings:
            s = settings[key]
            if s.is_secret and not unmask and s.value:
                out[key] = "****" + s.value[-4:] if len(s.value) > 4 else "****"
            else:
                out[key] = s.value or ""
        else:
            out[key] = SMTP_KEYS.get(key, {}).get("default", "")
    return out


async def upsert_setting(db: AsyncSession, key: str, value: str, is_secret: bool = False):
    """Insert or update a setting."""
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = value
        setting.is_secret = is_secret
    else:
        setting = SystemSetting(key=key, value=value, is_secret=is_secret)
        db.add(setting)


@_limiter.limit("30/minute")
@settings_router.get("/smtp")
async def get_smtp_settings(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Get SMTP configuration (passwords masked)."""
    data = await get_settings_dict(db, list(SMTP_KEYS.keys()))
    # Convert port to int for frontend
    try:
        data["smtp_port"] = int(data.get("smtp_port", "587"))
    except (ValueError, TypeError):
        data["smtp_port"] = 587
    # Convert tls to bool
    data["smtp_use_tls"] = data.get("smtp_use_tls", "true").lower() == "true"
    return data


@_limiter.limit("10/minute")
@settings_router.put("/smtp")
async def update_smtp_settings(
    body: SmtpSettingsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Update SMTP configuration."""
    await upsert_setting(db, "smtp_host", body.smtp_host)
    await upsert_setting(db, "smtp_port", str(body.smtp_port))
    await upsert_setting(db, "smtp_username", body.smtp_username)
    await upsert_setting(db, "smtp_from_email", body.smtp_from_email)
    await upsert_setting(db, "smtp_from_name", body.smtp_from_name)
    await upsert_setting(db, "smtp_use_tls", str(body.smtp_use_tls).lower())

    # Only update password if provided (not None / not empty placeholder)
    if body.smtp_password is not None and not body.smtp_password.startswith("****"):
        await upsert_setting(db, "smtp_password", body.smtp_password, is_secret=True)

    await db.commit()
    logger.info("SMTP settings updated via dashboard")

    return {"ok": True, "message": "SMTP settings saved"}


@_limiter.limit("5/minute")
@settings_router.post("/smtp/test")
async def test_smtp(
    body: TestEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Send a test email to verify SMTP configuration."""
    # Get actual (unmasked) settings from DB
    smtp_data = await get_settings_dict(db, list(SMTP_KEYS.keys()), unmask=True)

    host = smtp_data.get("smtp_host", "")
    if not host:
        raise HTTPException(status_code=400, detail="SMTP host not configured. Save settings first.")

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        port = int(smtp_data.get("smtp_port", "587"))
        username = smtp_data.get("smtp_username", "")
        password = smtp_data.get("smtp_password", "")
        from_email = smtp_data.get("smtp_from_email", "")
        from_name = smtp_data.get("smtp_from_name", "AI Assistant")
        use_tls = smtp_data.get("smtp_use_tls", "true").lower() == "true"

        # Build test email
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;">
  <tr><td style="background:linear-gradient(135deg,#06b6d4,#8b5cf6);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:600;">AI Assistant</h1>
  </td></tr>
  <tr><td style="padding:32px;">
    <h2 style="margin:0 0 16px;color:#f1f5f9;font-size:18px;">SMTP Test Successful!</h2>
    <p style="color:#cbd5e1;font-size:14px;line-height:1.6;">
      Your email configuration is working correctly. You will now receive notifications.
    </p>
    <div style="background:#0f172a;border-left:4px solid #22c55e;padding:16px;border-radius:8px;margin:16px 0;">
      <p style="margin:0;color:#22c55e;font-weight:600;">Configuration verified</p>
    </div>
  </td></tr>
  <tr><td style="padding:16px 32px;background:#0f172a;border-top:1px solid #334155;">
    <p style="margin:0;color:#64748b;font-size:12px;text-align:center;">
      AI Personal Assistant
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = "AI Assistant - SMTP Test"
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = body.to_email
        msg.attach(MIMEText(html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=host,
            port=port,
            username=username or None,
            password=password or None,
            use_tls=use_tls,
        )
        logger.info(f"SMTP test email sent to {body.to_email}")
        return {"ok": True, "message": f"Test email sent to {body.to_email}"}

    except ImportError:
        raise HTTPException(status_code=500, detail="aiosmtplib not installed on server")
    except Exception as e:
        logger.error(f"SMTP test failed: {e}")
        raise HTTPException(status_code=400, detail=f"SMTP test failed: {str(e)}")


# ─── Generic Settings (allowed_emails, etc.) ───
class GenericSettingRequest(BaseModel):
    value: str

@_limiter.limit("30/minute")
@settings_router.get("/{key}")
async def get_setting_value(key: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Get a single setting value by key."""
    val = await get_setting(db, key)
    return {"key": key, "value": val or ""}

@_limiter.limit("10/minute")
@settings_router.put("/{key}")
async def update_setting_value(key: str, body: GenericSettingRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Update a single setting value by key."""
    await upsert_setting(db, key, body.value)
    await db.commit()
    logger.info(f"Setting updated: {key}")
    return {"ok": True, "key": key}
