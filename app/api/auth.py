"""
Dashboard Authentication — Google OAuth token verification.
Verifies Google ID tokens and checks against allowed email list.
"""
import hashlib
import hmac
import json
import time
import logging
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
import httpx

from app.core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

auth_router = APIRouter(prefix="/api/v1/auth")
# Rate limiting
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings as _gs
_limiter = Limiter(key_func=get_remote_address, storage_uri=_gs().redis_url)



class GoogleTokenRequest(BaseModel):
    credential: str  # Google ID token from Sign-In


class SessionToken(BaseModel):
    token: str
    email: str
    name: str
    picture: str
    expires_at: int


def _create_session_token(email: str, name: str, picture: str) -> SessionToken:
    """Create a signed session token valid for 24 hours."""
    expires_at = int(time.time()) + 86400  # 24 hours
    payload = json.dumps({"email": email, "name": name, "picture": picture, "exp": expires_at})
    signature = hmac.new(settings.app_secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = f"{payload}|{signature}"
    return SessionToken(token=token, email=email, name=name, picture=picture, expires_at=expires_at)


def verify_session_token(token: str) -> dict | None:
    """Verify a session token and return the payload if valid."""
    try:
        parts = token.rsplit("|", 1)
        if len(parts) != 2:
            return None
        payload_str, signature = parts
        expected_sig = hmac.new(settings.app_secret_key.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


async def require_auth(request: Request):
    """FastAPI dependency: verify session token from Authorization header.
    Returns the decoded payload (email, name, etc.) if valid.
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = verify_session_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return payload


def require_permission(permission: str):
    """FastAPI dependency factory: checks user has a specific permission.
    Permissions come from TeamRole.permissions JSON field.
    If user has no role assigned, defaults to 'view' permission only.
    """
    async def _check_permission(request: Request):
        # First verify auth
        payload = await require_auth(request)
        email = payload.get("email", "")

        # Look up user's role and permissions
        from app.core.database import get_db
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select, text

        # Get db session manually
        from app.core.database import async_session
        async with async_session() as db:
            # Find user by email
            result = await db.execute(text(
                "SELECT u.role_id, tr.permissions FROM users u "
                "LEFT JOIN team_roles tr ON u.role_id = tr.id "
                "WHERE u.email = :email LIMIT 1"
            ).bindparams(email=email))
            row = result.first()

            if row and row[1]:
                # Parse permissions JSON
                try:
                    perms = json.loads(row[1]) if isinstance(row[1], str) else row[1]
                except (json.JSONDecodeError, TypeError):
                    perms = ["view"]
            else:
                # No role assigned — default to full access for admin users
                # (single-user app, be permissive)
                perms = ["view", "edit", "admin", "delete"]

            if permission not in perms and "admin" not in perms:
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient permissions. Required: {permission}"
                )

        return payload

    return _check_permission


@_limiter.limit("5/minute")
@auth_router.post("/google/verify")
async def verify_google_token(request: Request, body: GoogleTokenRequest):
    """
    Verify Google ID token or access token from the frontend Sign-In button.
    Supports both ID tokens (JWT) and access tokens (ya29.*) for web compatibility.
    Returns a session token if the email is in the allowed list.
    """
    credential = body.credential
    is_access_token = credential.startswith("ya29.") or credential.startswith("ya29/")

    try:
        async with httpx.AsyncClient() as client:
            if is_access_token:
                # Access token (from web google_sign_in) — verify via userinfo endpoint
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {credential}"},
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid Google access token")
                token_info = resp.json()
            else:
                # ID token (JWT) — verify via tokeninfo endpoint
                resp = await client.get(
                    f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
                )
                if resp.status_code != 200:
                    raise HTTPException(status_code=401, detail="Invalid Google token")
                token_info = resp.json()
    except httpx.RequestError as e:
        logger.error(f"Google token verification failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to verify Google token")

    email = token_info.get("email", "")
    name = token_info.get("name", email.split("@")[0])
    picture = token_info.get("picture", "")
    email_verified = token_info.get("email_verified", "false")

    # For access token userinfo response, email_verified is a boolean
    if isinstance(email_verified, bool):
        email_verified = str(email_verified).lower()

    # Check email is verified
    if str(email_verified).lower() != "true":
        raise HTTPException(status_code=401, detail="Email not verified")

    # Check email is in allowed list (static + dynamic from DB)
    allowed = [e.strip().lower() for e in settings.dashboard_allowed_emails.split(",")]
    try:
        from sqlalchemy import select as _sel, text as _txt
        from app.core.database import async_session as _asess
        async with _asess() as _db:
            _r = await _db.execute(_txt("SELECT value FROM system_settings WHERE key = 'allowed_emails' LIMIT 1"))
            _row = _r.first()
            if _row and _row[0]:
                allowed.extend([e.strip().lower() for e in _row[0].split(",") if e.strip()])
    except Exception:
        pass
    if email.lower() not in allowed:
        logger.warning(f"Dashboard access denied for: {email}")
        raise HTTPException(status_code=403, detail=f"Access denied. {email} is not authorized to access this dashboard.")

    # Create session token
    session = _create_session_token(email, name, picture)
    logger.info(f"Dashboard login: {email}")
    return session


@_limiter.limit("30/minute")
@auth_router.get("/verify")
async def verify_session(request: Request):
    """Verify an existing session token from the Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No session token")

    token = auth[7:]
    payload = verify_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    return {"valid": True, "email": payload.get("email"), "name": payload.get("name")}


@_limiter.limit("30/minute")
@auth_router.get("/client-id")
async def get_google_client_id(request: Request):
    """Return the Google Client ID for the frontend Sign-In button."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google Client ID not configured")
    return {"client_id": settings.google_client_id}


@_limiter.limit("10/minute")
@auth_router.get("/google/callback")
async def google_oauth_callback(code: str, request: Request):
    """
    Handle Google OAuth2 redirect callback.
    Exchanges authorization code for tokens, verifies email, and redirects to dashboard.
    """
    from fastapi.responses import RedirectResponse
    from urllib.parse import urlencode, quote

    redirect_uri = str(request.url_for("google_oauth_callback"))
    # Force HTTPS in production
    if redirect_uri.startswith("http://") and settings.is_production:
        redirect_uri = redirect_uri.replace("http://", "https://", 1)

    # Exchange code for tokens
    try:
        async with httpx.AsyncClient() as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            if token_resp.status_code != 200:
                logger.error(f"Google token exchange failed: {token_resp.text}")
                return RedirectResponse(url="/?login_error=token_exchange_failed")
            tokens = token_resp.json()

            # Get user info
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            if userinfo_resp.status_code != 200:
                return RedirectResponse(url="/?login_error=userinfo_failed")
            userinfo = userinfo_resp.json()
    except httpx.RequestError as e:
        logger.error(f"Google OAuth callback error: {e}")
        return RedirectResponse(url="/?login_error=network_error")

    email = userinfo.get("email", "")
    name = userinfo.get("name", email.split("@")[0])
    picture = userinfo.get("picture", "")
    verified = userinfo.get("verified_email", False)

    if not verified:
        return RedirectResponse(url="/?login_error=email_not_verified")

    # Check allowed emails (static + dynamic from DB)
    allowed = [e.strip().lower() for e in settings.dashboard_allowed_emails.split(",")]
    try:
        from sqlalchemy import text as _txt
        from app.core.database import async_session as _asess
        async with _asess() as _db:
            _r = await _db.execute(_txt("SELECT value FROM system_settings WHERE key = 'allowed_emails' LIMIT 1"))
            _row = _r.first()
            if _row and _row[0]:
                allowed.extend([e.strip().lower() for e in _row[0].split(",") if e.strip()])
    except Exception:
        pass
    if email.lower() not in allowed:
        logger.warning(f"Dashboard access denied for: {email}")
        return RedirectResponse(url="/?login_error=access_denied")

    # Create session and redirect with token data
    session = _create_session_token(email, name, picture)
    session_data = json.dumps({
        "token": session.token,
        "email": session.email,
        "name": session.name,
        "picture": session.picture,
        "expires_at": session.expires_at,
    })
    logger.info(f"Dashboard login (OAuth redirect): {email}")
    return RedirectResponse(url=f"/?session_token={quote(session_data)}")
