import uuid
from typing import Dict, Optional
import asyncio


# In-memory session storage
# {session_id: {"image_data": bytes, "created_at": timestamp}}
_sessions: Dict[str, Dict] = {}
_session_lock = asyncio.Lock()


async def create_session(image_data: bytes) -> str:
    """Create a new session with image data."""
    session_id = str(uuid.uuid4())[:12]
    async with _session_lock:
        _sessions[session_id] = {
            "image_data": image_data,
            "created_at": asyncio.get_event_loop().time()
        }
    return session_id


async def get_session(session_id: str) -> Optional[bytes]:
    """Get image data for a session."""
    async with _session_lock:
        session = _sessions.get(session_id)
        if session:
            return session["image_data"]
        return None


async def delete_session(session_id: str):
    """Delete a session after use."""
    async with _session_lock:
        _sessions.pop(session_id, None)


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