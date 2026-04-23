# Learning Log - Gemini Vision Sprint

## What We Built
AI-powered image analysis web app using Gemini API with FastAPI backend and vanilla HTML/JS frontend.

## Key Decisions & Learnings

### 1. Tech Stack: FastAPI over Go
- Chose FastAPI for faster development
- Python ecosystem easier for Gemini integration
- Gunicorn with uvicorn worker needed for ASGI

### 2. Model: gemini-3-flash-preview
- gemini-2.5-flash had quota issues (503 errors)
- gemini-3-flash-preview worked
- code_execution tool enables Agentic Vision

### 3. Multi-Key Rotation
- Single API key hits quota frequently
- Implemented automatic failover: `GEMINI_API_KEYS=key1,key2,key3`
- Rotates on 429/503 errors

### 4. Streaming (SSE)
- Agentic Vision shows Think → Act → Observe steps
- Server-Sent Events for real-time step-by-step display
- 300ms delay makes streaming visible

### 5. Error Handling
- Structured error codes: E001, E002, E003, E004
- {code, message} format prevents API key leaks
- Full errors logged server-side only

### 6. Session/Multi-turn
- In-memory session storage
- Session ID for follow-up questions
- Cleanup after use

## Challenges

### CORS Issue on Render
- Gunicorn needed ASGI worker: `gunicorn -k uvicorn.workers.UvicornWorker`
- Or use uvicorn directly as start command

### Static File Path
- `Path(__file__).parent.parent / "static"` not `Path(__file__).parent / "static"`
- Had to fix relative path for Render deployment

### API Rate Limits
- gemini-3-flash-preview has strict quotas
- Multiple keys critical for production
- 503 errors common under load

### File Upload Size
- Both client (5MB) and server validation
- FastAPI UploadFile.size not always populated
- Read content and check len()

## What Worked Well

1. **Fast scaffolding** - Opencode + FastAPI quick prototype
2. **SSE streaming** - Real-time UI updates
3. **Error codes** - Debug without leaking secrets
4. **Docker** - Cross-platform deployment

## What Didn't Work

1. **go + Fiber** - Switched to FastAPI mid-sprint
2. **gemini-2.5-flash** - Quota issues
3. **gunicorn sync worker** - Needed uvicorn worker for ASGI
4. **Render static files** - Had to use FileResponse

## Future Improvements

1. **Rate limit handling** - Better retry logic with exponential backoff
2. **Database sessions** - Redis for production multi-turn
3. **Image preprocessing** - Resize before sending to Gemini
4. **Cache responses** - Same image + question
5. **WebSocket** - Instead of SSE for streaming
6. **Multi-region** - Deploy to multiple Render regions

## Files Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   ├── gemini_client.py # Gemini API client
│   ├── middleware.py  # Request ID middleware
│   ├── sessions.py    # Session management
│   └── errors.py       # Error codes
├── static/
│   └── index.html     # Frontend
├── Dockerfile
├── requirements.txt
└── README.md
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/api/analyze` | POST | Standard analysis |
| `/api/analyze/agentic` | POST | Agentic analysis |
| `/api/analyze/agentic/stream` | POST | Streaming SSE |
| `/api/analyze/session` | POST | Create session |
| `/api/analyze/followup` | POST | Follow-up question |