# Gemini Vision

AI-powered image analysis web app with Gemini API. Upload an image and ask questions about it.

## Features

- **Standard Mode**: Simple image Q&A with single response
- **Agentic Mode**: Code execution with step-by-step streaming timeline
  - See Thinking → Code Execution → Output → Observe in real-time
  - "Gemini is Thinking..." indicator between SSE steps
  - Final Answer labeled on last thinking step
- **Multi-turn Conversation**: Continue asking follow-up questions on the same image
  - Separate sessions for Standard and Agentic modes
  - Cards accumulate below follow-up form
- Client-side 5MB validation
- Server-side validation
- CORS enabled
- Structured JSON logging with request_id for full traceability

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla HTML/JS
- **Deployment**: Render (Docker)
- **AI**: Gemini 3 Flash Preview with Code Execution

## Quick Start

### Local Development

```bash
# Clone and enter
git clone https://github.com/xaris-tech/wizy-test.git
cd wizy-test

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set API key
cp .env.example .env
# Edit .env with your API key

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Open http://localhost:8080

### With Docker

```bash
docker build -t gemini-vision .
docker run -p 8080:8080 -e GEMINI_API_KEY=your_key gemini-vision
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web UI |
| `/health` | GET | Health check |
| `/api/analyze` | POST | Standard image analysis |
| `/api/analyze/agentic` | POST | Agentic with code execution |
| `/api/analyze/agentic/stream` | POST | Agentic with SSE streaming |
| `/api/analyze/session` | POST | Create session for multi-turn |
| `/api/analyze/followup` | POST | Standard follow-up question |
| `/api/analyze/agentic/followup` | POST | Agentic follow-up with streaming |

### Analyze API (Standard)

```bash
curl -X POST http://localhost:8080/api/analyze \
  -F "file=@image.jpg" \
  -F "question=What's in this image?"
```

Response:
```json
{"answer": "A red square..."}
```

### Agentic Stream API

```bash
curl -X POST http://localhost:8080/api/analyze/agentic/stream \
  -F "file=@image.jpg" \
  -F "question=Count the items"
```

Response (SSE streaming):
```
data: {"type": "think", "content": "I'll analyze the image..."}
data: {"type": "code", "content": "from PIL import Image..."}
data: {"type": "output", "content": "Found 5 objects"}
data: {"type": "done"}
```

### Session Management

```bash
# Create session (returns session_id)
curl -X POST http://localhost:8080/api/analyze/session \
  -F "file=@image.jpg" \
  -F "agentic=true"

# Follow-up with session_id
curl -X POST http://localhost:8080/api/analyze/agentic/followup \
  -d "session_id=abc123" \
  -d "question=What color is the first object?"
```

## Deployment (Render)

1. Create GitHub repo
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect GitHub repo
4. Add environment variable: `GEMINI_API_KEY` (or `GEMINI_API_KEYS` for multiple)
5. Build Command: (leave empty - auto-detects Dockerfile)
6. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
7. Click Create

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app with all endpoints
│   ├── gemini_client.py # Gemini API client with key rotation
│   ├── middleware.py    # Request ID middleware
│   ├── logger.py        # Structured JSON logging
│   └── sessions.py      # In-memory session storage
├── static/
│   └── index.html       # Frontend with SSE streaming
├── Dockerfile
├── requirements.txt
├── .env.example
└── .gitignore
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Single API key |
| `GEMINI_API_KEYS` | Multiple keys (comma-separated) for auto-failover |
| `PORT` | Server port (default: 8080) |

### Multiple API Keys (Failover)

To use multiple API keys (auto-rotates on quota errors):

```bash
# In .env or Render dashboard
GEMINI_API_KEYS=key1,key2,key3
```

When one key hits quota (429/503), the system automatically rotates to the next key.

## Get API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API key
3. Use in local `.env` or Render dashboard

## Structured Logging

All logs are JSON-formatted with request_id for full traceability:

```json
{
  "timestamp": "2026-04-23T05:21:10.215694Z",
  "level": "INFO",
  "request_id": "49d37c69-af3",
  "message": "Agentic stream request started",
  "module": "stream"
}
```

Pass `X-Request-ID` header to use custom request ID, or one will be generated automatically.

## License

MIT