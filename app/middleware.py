import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logger import get_logger, set_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Add request ID to each request for tracking with structured logging."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Extract request_id from header or generate new one
        request_id = request.headers.get("x-request-id")
        if not request_id:
            request_id = str(uuid.uuid4())[:12]
        
        # Store in request state for route handlers
        request.state.request_id = request_id
        
        # Set in context for structured logging
        old_value = set_request_id(request_id)
        
        logger = get_logger("middleware")
        logger.info(f"Incoming request", method=request.method, path=request.url.path)
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            # Restore previous context
            set_request_id(old_value)


def get_request_id(request: Request) -> str:
    """Get request ID from state."""
    return getattr(request.state, "request_id", "unknown")