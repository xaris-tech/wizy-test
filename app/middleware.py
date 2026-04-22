import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request ID to each request for tracking."""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        
        logger.info(f"[{request_id}] {request.method} {request.url.path}")
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        
        return response


def get_request_id(request: Request) -> str:
    """Get request ID from state."""
    return getattr(request.state, "request_id", "unknown")