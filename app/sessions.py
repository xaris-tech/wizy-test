import uuid
from typing import Dict, Optional, List
import asyncio

from app.logger import get_logger, get_request_id as get_ctx_request_id


_sessions: Dict[str, Dict] = {}
_session_lock = asyncio.Lock()


async def create_session(image_data: bytes, use_agentic: bool = False) -> str:
    """Create a new session with image data."""
    session_id = str(uuid.uuid4())[:12]
    async with _session_lock:
        _sessions[session_id] = {
            "image_data": image_data,
            "history": [],
            "use_agentic": use_agentic,
            "created_at": asyncio.get_event_loop().time()
        }
    logger = get_logger("sessions")
    logger.info("Session created", session_id=session_id, use_agentic=use_agentic)
    return session_id


async def get_session(session_id: str) -> Optional[Dict]:
    """Get session data for a session."""
    async with _session_lock:
        session = _sessions.get(session_id)
        if session:
            return session
    logger = get_logger("sessions")
    logger.warning("Session not found", session_id=session_id)
    return None


async def add_to_history(session_id: str, role: str, content: str):
    """Add a message to session history."""
    async with _session_lock:
        session = _sessions.get(session_id)
        if session:
            session["history"].append({"role": role, "content": content})


async def delete_session(session_id: str):
    """Delete a session after use."""
    async with _session_lock:
        _sessions.pop(session_id, None)
    logger = get_logger("sessions")
    logger.info("Session deleted", session_id=session_id)


async def cleanup_old_sessions(max_age_seconds: int = 3600):
    """Clean up sessions older than max_age_seconds."""
    import time
    current_time = time.time()
    async with _session_lock:
        to_delete = [
            sid for sid, data in _sessions.items()
            if current_time - data.get("created_at", 0) > max_age_seconds
        ]
        for sid in to_delete:
            _sessions.pop(sid, None)
    if to_delete:
        logger = get_logger("sessions")
        logger.info("Cleaned up old sessions", count=len(to_delete))