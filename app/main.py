import os
import logging
import json
import base64
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from dataclasses import asdict
from dotenv import load_dotenv
import httpx

from app.gemini_client import get_gemini_client

load_dotenv()

# Support single key or multiple keys (comma-separated)
single_key = os.getenv("GEMINI_API_KEY", "")
multi_keys = os.getenv("GEMINI_API_KEYS", "")

if not single_key and not multi_keys:
    logging.critical("GEMINI_API_KEY or GEMINI_API_KEYS is required. Set in .env or environment.")
    raise ValueError("GEMINI_API_KEY or GEMINI_API_KEYS is required")

PORT = int(os.getenv("PORT", "8080"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Gemini Vision API")
    yield
    logger.info("Shutting down Gemini Vision API")


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def catch_exceptions(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        logger.error(f"Unhandled error: {e}")
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    from fastapi.responses import FileResponse
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Gemini Vision API - upload an image and ask questions"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/api/analyze")
async def analyze(
    file: UploadFile = File(...),
    question: str = Form(...)
):
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    client = get_gemini_client()
    try:
        answer = client.analyze(contents, question)
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")


@app.post("/api/analyze/agentic")
async def analyze_agentic(
    file: UploadFile = File(...),
    question: str = Form(...)
):
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    client = get_gemini_client()
    try:
        result = client.analyze_agentic(contents, question)
        return asdict(result)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise HTTPException(status_code=500, detail="Analysis failed. Please try again.")


async def generate_agentic_stream(image_data: bytes, question: str, client) -> AsyncGenerator[str, None]:
    """Stream agentic steps as they're generated using SSE."""
    image_b64 = base64.b64encode(image_data).decode("utf-8")

    # For streaming, we'd need to use the streaming API
    # For now, let's use a simpler approach: stream partial results
    # The model generates all at once, but we can chunk the response
    
    payload = {
        "contents": [{
            "parts": [
                {"text": question},
                {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}}
            ]
        }],
        "tools": [{"code_execution": {}}]
    }

    with httpx.Client(timeout=120.0) as hpClient:
        response = hpClient.post(client.current_url, json=payload)
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates", [])
        if not candidates:
            yield "data: " + json.dumps({"error": "No response from Gemini"}) + "\n\n"
            return

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        for i, part in enumerate(parts):
            step = {}
            if "executableCode" in part:
                step = {"type": "code", "content": part["executableCode"].get("code", ""), "language": "python"}
            elif "codeExecutionResult" in part:
                result = part["codeExecutionResult"]
                step = {"type": "output", "content": result.get("output", ""), "outcome": result.get("outcome", "")}
                if "inlineData" in result:
                    step["image_data"] = result["inlineData"].get("data", "")
                    step["image_mime_type"] = result["inlineData"].get("mimeType", "image/png")
            elif "inlineData" in part:
                step = {"type": "observe", "content": "Intermediate image", "image_data": part["inlineData"].get("data", ""), "image_mime_type": part["inlineData"].get("mimeType", "image/png")}
            elif "text" in part and part.get("text"):
                step = {"type": "think", "content": part.get("text", "")}

            if step:
                yield "data: " + json.dumps(step) + "\n\n"
                # Small delay to make streaming visible
                import asyncio
                await asyncio.sleep(0.3)


@app.post("/api/analyze/agentic/stream")
async def analyze_agentic_stream(
    file: UploadFile = File(...),
    question: str = Form(...)
):
    """Stream agentic analysis steps one by one via SSE."""
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    client = get_gemini_client()

    async def event_generator():
        try:
            async for chunk in generate_agentic_stream(contents, question, client):
                yield chunk
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield "data: " + json.dumps({"error": "Analysis failed"}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)