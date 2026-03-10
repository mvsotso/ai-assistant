"""
Email Service — SMTP email notifications with HTML templates.
Reads SMTP config from database (system_settings) first, then falls back to .env.
"""
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def _get_smtp_config() -> dict:
    """Get SMTP configuration from database first, then fall back to .env."""
    env = get_settings()

    # Try database settings first
    try:
        from app.core.database import async_session
        from app.models.system_setting import SystemSetting

        async with async_session() as db:
            result = await db.execute(
                select(SystemSetting).where(
                    SystemSetting.key.in_([
                        "smtp_host", "smtp_port", "smtp_username",
                        "smtp_password", "smtp_from_email", "smtp_from_name",
                        "smtp_use_tls",
                    ])
                )
            )
            db_settings = {s.key: s.value for s in result.scalars().all()}

            # If DB has smtp_host configured, use DB settings
            if db_settings.get("smtp_host"):
                return {
                    "host": db_settings.get("smtp_host", ""),
                    "port": int(db_settings.get("smtp_port", "587")),
                    "username": db_settings.get("smtp_username", ""),
                    "password": db_settings.get("smtp_password", ""),
                    "from_email": db_settings.get("smtp_from_email", ""),
                    "from_name": db_settings.get("smtp_from_name", "AI Assistant"),
                    "use_tls": db_settings.get("smtp_use_tls", "true").lower() == "true",
                }
    except Exception as e:
        logger.debug(f"DB settings lookup failed, using env: {e}")

    # Fall back to environment variables
    return {
        "host": env.smtp_host,
        "port": env.smtp_port,
        "username": env.smtp_username,
        "password": env.smtp_password,
        "from_email": env.smtp_from_email,
        "from_name": env.smtp_from_name,
        "use_tls": env.smtp_use_tls,
    }


async def _get_email_prefs(db: AsyncSession, user_email: str):
    """Get email preferences for a user, returns None if not found."""
    from app.models.email_preference import EmailPreference
    result = await db.execute(
        select(EmailPreference).where(EmailPreference.user_email == user_email)
    )
    return result.scalar_one_or_none()


def _build_html(title: str, body_content: str) -> str:
    """Build HTML email with inline CSS matching dashboard dark theme."""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width"></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0f172a;padding:20px 0;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0" style="background:#1e293b;border-radius:12px;overflow:hidden;border:1px solid #334155;">
  <tr><td style="background:linear-gradient(135deg,#06b6d4,#8b5cf6);padding:24px 32px;">
    <h1 style="margin:0;color:#fff;font-size:20px;font-weight:600;">AI Assistant</h1>
  </td></tr>
  <tr><td style="padding:32px;">
    <h2 style="margin:0 0 16px;color:#f1f5f9;font-size:18px;font-weight:600;">{title}</h2>
    <div style="color:#cbd5e1;font-size:14px;line-height:1.6;">{body_content}</div>
  </td></tr>
  <tr><td style="padding:16px 32px;background:#0f172a;border-top:1px solid #334155;">
    <p style="margin:0;color:#64748b;font-size:12px;text-align:center;">
      AI Personal Assistant &bull; <a href="https://aia.rikreay24.com" style="color:#06b6d4;text-decoration:none;">Open Dashboard</a>
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


async def send_email(to: str, subject: str, html_body: str):
    """Send an email via SMTP. Silently skips if SMTP not configured."""
    cfg = await _get_smtp_config()
    if not cfg["host"]:
        return  # SMTP not configured

    try:
        import aiosmtplib

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = to
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=cfg["host"],
            port=cfg["port"],
            username=cfg["username"] or None,
            password=cfg["password"] or None,
            use_tls=cfg["use_tls"],
        )
        logger.info(f"Email sent to {to}: {subject}")
    except ImportError:
        logger.warning("aiosmtplib not installed, skipping email")
    except Exception as e:
        logger.error(f"Email send failed to {to}: {e}")


async def send_task_assigned_email(db: AsyncSession, to_email: str, task_title: str, assignee: str, due_date=None):
    """Send task assignment notification email."""
    if not to_email:
        return
    prefs = await _get_email_prefs(db, to_email)
    if prefs and (not prefs.email_enabled or not prefs.task_assigned):
        return

    due_str = due_date.strftime("%b %d, %Y %H:%M") if due_date else "No due date"
    body = f"""
    <p>A task has been assigned to <strong style="color:#06b6d4;">{assignee}</strong>:</p>
    <div style="background:#0f172a;border-left:4px solid #06b6d4;padding:16px;border-radius:8px;margin:16px 0;">
      <p style="margin:0;color:#f1f5f9;font-weight:600;font-size:16px;">{task_title}</p>
      <p style="margin:8px 0 0;color:#94a3b8;font-size:13px;">Due: {due_str}</p>
    </div>
    <p><a href="https://aia.rikreay24.com" style="display:inline-block;background:#06b6d4;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;">View Task</a></p>
    """
    await send_email(to_email, f"Task Assigned: {task_title}", _build_html("Task Assigned", body))


async def send_task_status_email(db: AsyncSession, to_email: str, task_title: str, old_status: str, new_status: str):
    """Send task status change notification email."""
    if not to_email:
        return
    prefs = await _get_email_prefs(db, to_email)
    if prefs and (not prefs.email_enabled or not prefs.task_status_change):
        return

    status_colors = {"todo": "#94a3b8", "in_progress": "#3b82f6", "review": "#f59e0b", "done": "#10b981"}
    new_color = status_colors.get(new_status, "#94a3b8")
    body = f"""
    <p>Task status has been updated:</p>
    <div style="background:#0f172a;border-left:4px solid {new_color};padding:16px;border-radius:8px;margin:16px 0;">
      <p style="margin:0;color:#f1f5f9;font-weight:600;font-size:16px;">{task_title}</p>
      <p style="margin:8px 0 0;color:#94a3b8;font-size:13px;">
        <span style="text-decoration:line-through;">{old_status.replace('_',' ').title()}</span>
        &rarr; <span style="color:{new_color};font-weight:600;">{new_status.replace('_',' ').title()}</span>
      </p>
    </div>
    """
    await send_email(to_email, f"Status Update: {task_title}", _build_html("Task Status Changed", body))


async def send_reminder_email(db: AsyncSession, to_email: str, message: str):
    """Send reminder notification email."""
    if not to_email:
        return
    prefs = await _get_email_prefs(db, to_email)
    if prefs and (not prefs.email_enabled or not prefs.reminder_due):
        return

    body = f"""
    <div style="background:#0f172a;border-left:4px solid #f59e0b;padding:16px;border-radius:8px;margin:16px 0;">
      <p style="margin:0;color:#f1f5f9;font-size:15px;">{message}</p>
    </div>
    <p><a href="https://aia.rikreay24.com" style="display:inline-block;background:#f59e0b;color:#0f172a;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Open Dashboard</a></p>
    """
    await send_email(to_email, f"Reminder: {message[:60]}", _build_html("Reminder", body))


async def send_daily_summary_email(db: AsyncSession, to_email: str, summary_text: str):
    """Send daily summary email."""
    if not to_email:
        return
    prefs = await _get_email_prefs(db, to_email)
    if prefs and (not prefs.email_enabled or not prefs.daily_summary):
        return

    # Convert markdown-like text to simple HTML
    html_summary = summary_text.replace("\n", "<br>")
    body = f"""
    <div style="color:#cbd5e1;font-size:14px;line-height:1.8;">{html_summary}</div>
    <p style="margin-top:24px;"><a href="https://aia.rikreay24.com" style="display:inline-block;background:#8b5cf6;color:#fff;padding:10px 24px;border-radius:8px;text-decoration:none;font-weight:600;">Open Dashboard</a></p>
    """
    await send_email(to_email, "Daily Summary - AI Assistant", _build_html("Daily Summary", body))
