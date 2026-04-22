# Gemini Vision

AI-powered image analysis web app with Gemini API. Upload an image and ask questions about it.

## Features

- **Standard Mode**: Simple image Q&A
- **Agentic Mode**: Code execution - see the model's thinking process with step-by-step timeline
- Client-side 5MB validation
- Server-side validation
- CORS enabled

## Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: Vanilla HTML/JS
- **Deployment**: Render (Docker)
- **AI**: Gemini 3 Flash Preview

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
export GEMINI_API_KEY=your_key_here  # On Windows: set GEMINI_API_KEY=your_key_here

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

### Analyze API

```bash
curl -X POST http://localhost:8080/api/analyze \
  -F "file=@image.jpg" \
  -F "question=What's in this image?"
```

Response:
```json
{"answer": "A red square..."}
```

### Agentic API

```bash
curl -X POST http://localhost:8080/api/analyze/agentic \
  -F "file=@image.jpg" \
  -F "question=Calculate something with this?"
```

Response:
```json
{
  "answer": "The first 20 prime numbers are...",
  "steps": [
    {"type": "code", "content": "def is_prime(n)..."},
    {"type": "output", "content": "[2, 3, 5, 7...]"},
    {"type": "think", "content": "Based on the properties..."}
  ]
}
```

## Deployment (Render)

1. Create GitHub repo
2. Go to [render.com](https://render.com) → New → Web Service
3. Connect GitHub repo
4. Add environment variable: `GEMINI_API_KEY`
5. Build Command: (leave empty - auto-detects Dockerfile)
6. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port 8080`
7. Click Create

Or with gunicorn (requires uvicorn in requirements.txt):
```
gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8080 app.main:app
```

## Project Structure

```
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app
│   └── gemini_client.py # Gemini API client
├── static/
│   └── index.html     # Frontend
├── Dockerfile
├── requirements.txt
├── .env.example
└── .gitignore
```

## Get API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API key
3. Use in local `.env` or Render dashboard

## License

MIT