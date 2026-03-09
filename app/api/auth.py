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


@auth_router.post("/google/verify")
async def verify_google_token(body: GoogleTokenRequest):
    """
    Verify Google ID token from the frontend Sign-In button.
    Returns a session token if the email is in the allowed list.
    """
    # Verify the Google ID token
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={body.credential}"
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

    # Check email is verified
    if str(email_verified).lower() != "true":
        raise HTTPException(status_code=401, detail="Email not verified")

    # Check email is in allowed list
    allowed = [e.strip().lower() for e in settings.dashboard_allowed_emails.split(",")]
    if email.lower() not in allowed:
        logger.warning(f"Dashboard access denied for: {email}")
        raise HTTPException(status_code=403, detail=f"Access denied. {email} is not authorized to access this dashboard.")

    # Create session token
    session = _create_session_token(email, name, picture)
    logger.info(f"Dashboard login: {email}")
    return session


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


@auth_router.get("/client-id")
async def get_google_client_id():
    """Return the Google Client ID for the frontend Sign-In button."""
    if not settings.google_client_id:
        raise HTTPException(status_code=500, detail="Google Client ID not configured")
    return {"client_id": settings.google_client_id}


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

    # Check allowed emails
    allowed = [e.strip().lower() for e in settings.dashboard_allowed_emails.split(",")]
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
