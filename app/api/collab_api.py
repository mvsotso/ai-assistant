"""
Collaboration API - watchers, activity feed, and WebSocket.
"""
import json
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from app.core.database import get_db
from app.api.auth import require_auth, verify_session_token
from app.services.collab_svc import collab_service

from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()
limiter = Limiter(key_func=get_remote_address, storage_uri=_settings.redis_url)

router = APIRouter(prefix="/api/v1", tags=["collaboration"])

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)
        for conn in disconnected:
            self.disconnect(conn)

ws_manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = ""):
    """WebSocket for real-time task updates."""
    if not token:
        await websocket.close(code=1008)
        return
    payload = verify_session_token(token)
    if not payload:
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or handle client messages
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except (json.JSONDecodeError, TypeError):
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@limiter.limit("20/minute")
@router.post("/tasks/{task_id}/watch")
async def watch_task(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Watch a task for updates."""
    added = await collab_service.watch_task(db, task_id, _auth.get("email", ""))
    await db.commit()
    return {"ok": True, "watching": True, "added": added}


@limiter.limit("20/minute")
@router.delete("/tasks/{task_id}/watch")
async def unwatch_task(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Stop watching a task."""
    removed = await collab_service.unwatch_task(db, task_id, _auth.get("email", ""))
    await db.commit()
    return {"ok": True, "watching": False, "removed": removed}


@limiter.limit("30/minute")
@router.get("/tasks/{task_id}/watchers")
async def get_watchers(
    request: Request, task_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get watchers for a task."""
    watchers = await collab_service.get_watchers(db, task_id)
    is_watching = await collab_service.is_watching(db, task_id, _auth.get("email", ""))
    return {"watchers": watchers, "is_watching": is_watching}


@limiter.limit("30/minute")
@router.get("/activity")
async def get_activity(
    request: Request,
    limit: int = 50,
    entity_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: dict = Depends(require_auth),
):
    """Get activity feed."""
    feed = await collab_service.get_activity_feed(db, limit, entity_type)
    return {"activities": feed}
