import os
import logging
import json
import base64
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, StreamingResponse
from dataclasses import asdict
from dotenv import load_dotenv
import httpx

from app.gemini_client import get_gemini_client
from app.middleware import RequestIDMiddleware

# Rate limiting semaphore for streaming requests
stream_semaphore = asyncio.Semaphore(2)

import time

load_dotenv()


def get_error_message(e: Exception) -> str:
    """Extract readable error from exception."""
    error_str = str(e)
    if "429" in error_str:
        return "Rate limited (429). Please wait a moment."
    if "503" in error_str:
        return "Service unavailable (503). Please try again."
    if "400" in error_str:
        return "Bad request (400). Please check your input."
    if "401" in error_str or "403" in error_str:
        return "Authentication error. Check your API key."
    return "Analysis failed. Please try again."

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

app.add_middleware(RequestIDMiddleware)


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
        raise HTTPException(status_code=500, detail=get_error_message(e))


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
        raise HTTPException(status_code=500, detail=get_error_message(e))


async def generate_agentic_stream(image_data: bytes, question: str, client) -> AsyncGenerator[str, None]:
    """Stream agentic steps as they're generated using Gemini's streaming API with true streaming."""
    from app.gemini_client import GEMINI_API_STREAM_URL
    
    image_b64 = base64.b64encode(image_data).decode("utf-8")
    
    stream_url = f"{GEMINI_API_STREAM_URL}?key={client.current_key}"
    
    payload = {
        "contents": [{
            "parts": [
                {"text": question},
                {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}}
            ]
        }],
        "tools": [{"code_execution": {}}],
        "systemInstruction": {
            "parts": [{"text": "Use code execution to analyze images. Show your thinking by writing and running Python code to inspect the image."}]
        }
    }
    
    retry_count = 0
    max_retries = 3
    
    async with stream_semaphore:
        while retry_count <= max_retries:
            try:
                async with httpx.AsyncClient(timeout=120.0) as hpClient:
                    async with hpClient.stream("POST", stream_url, json=payload) as response:
                        logger.info(f"Stream response status: {response.status_code}")
                        
                        if response.status_code in (429, 503):
                            if retry_count < max_retries:
                                wait_time = 2 ** retry_count
                                logger.warning(f"Rate limit (429/503) on key #{client.current_key_index + 1}. Waiting {wait_time}s...")
                                await asyncio.sleep(wait_time)
                                retry_count += 1
                                continue
                            else:
                                logger.warning(f"Max retries for key #{client.current_key_index + 1}, rotating...")
                                client.rotate_key()
                                stream_url = f"{GEMINI_API_STREAM_URL}?key={client.current_key}"
                                retry_count = 0
                                continue
                        
                        response.raise_for_status()
                        
                        # True streaming - process each line as it arrives
                        final_answer = ""
                        buffered_think = ""
                        json_buffer = ""
                        depth = 0
                        line_count = 0
                        
                        async for line in response.aiter_lines():
                            line_count += 1
                            if not line or line == '[' or line == ']':
                                continue
                            
                            json_buffer += line + "\n"
                            
                            # Track JSON braces to handle multi-line objects
                            for char in line:
                                if char == '{':
                                    depth += 1
                                elif char == '}':
                                    depth -= 1
                            
                            if depth == 0 and json_buffer.strip():
                                logger.info(f"Line {line_count}: complete JSON, depth=0")
                                # Complete JSON object
                                try:
                                    data = json.loads(json_buffer)
                                except json.JSONDecodeError as e:
                                    logger.warning(f"JSON decode error: {e}, buffer: {json_buffer[:100]}")
                                    json_buffer = ""
                                    depth = 0
                                    continue
                                
                                candidates = data.get("candidates", [])
                                if not candidates:
                                    json_buffer = ""
                                    continue
                                
                                content = candidates[0].get("content", {})
                                parts = content.get("parts", [])
                                
                                for part in parts:
                                    step = {}
                                    if "executableCode" in part:
                                        if buffered_think:
                                            yield "data: " + json.dumps({"type": "think", "content": buffered_think}) + "\n\n"
                                            await asyncio.sleep(0.05)
                                            buffered_think = ""
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
                                        buffered_think += part.get("text", "")
                                        final_answer = part.get("text", "")

                                    if step:
                                        yield "data: " + json.dumps(step) + "\n\n"
                                        await asyncio.sleep(0.05)
                                
                                json_buffer = ""
                        
                        # Flush remaining think
                        if buffered_think:
                            yield "data: " + json.dumps({"type": "think", "content": buffered_think}) + "\n\n"
                        
                        return
                        
            except httpx.HTTPStatusError as e:
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"Error: {e}. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                yield "data: " + json.dumps({"error": get_error_message(e)}) + "\n\n"
                return
            except Exception as e:
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.warning(f"Error: {e}. Waiting {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                yield "data: " + json.dumps({"error": get_error_message(e)}) + "\n\n"
                return


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
            yield "data: " + json.dumps({"error": get_error_message(e)}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/analyze/session")
async def create_session_endpoint(
    file: UploadFile = File(...),
    agentic: bool = Form(False)
):
    """Create a session and return session_id for multi-turn conversation."""
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Max 5MB.")

    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    from app.sessions import create_session as create_session_func
    session_id = await create_session_func(contents, use_agentic=agentic)
    return {"session_id": session_id}


@app.post("/api/analyze/agentic/followup")
async def agentic_followup(
    session_id: str = Form(...),
    question: str = Form(...)
):
    """Continue agentic conversation with existing session using streaming."""
    from app.sessions import get_session as get_session_func
    from app.sessions import add_to_history
    
    session = await get_session_func(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session expired. Please upload a new image.")

    image_data = session.get("image_data")
    history = session.get("history", [])
    
    client = get_gemini_client()

    async def event_generator():
        try:
            # Add user question to history
            await add_to_history(session_id, "user", question)
            
            # Build conversation context from history
            conversation_parts = []
            for msg in history:
                conversation_parts.append({"text": f"{msg['role']}: {msg['content']}"})
            conversation_parts.append({"text": question})
            
            # Stream the response
            async for chunk in generate_agentic_stream_with_history(image_data, conversation_parts, client):
                yield chunk
            
            # Add assistant response to history (we need to capture it)
            yield "data: " + json.dumps({"type": "done"}) + "\n\n"
        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield "data: " + json.dumps({"error": get_error_message(e)}) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


async def generate_agentic_stream_with_history(image_data: bytes, conversation_parts: List[str], client) -> AsyncGenerator[str, None]:
    """Stream agentic steps with conversation history."""
    from app.gemini_client import GEMINI_API_STREAM_URL
    
    image_b64 = base64.b64encode(image_data).decode("utf-8")
    
    stream_url = f"{GEMINI_API_STREAM_URL}?key={client.current_key}"
    
    # Build contents with image and conversation history
    contents = []
    contents.append({
        "parts": [
            {"inlineData": {"mimeType": "image/jpeg", "data": image_b64}}
        ]
    })
    
    # Add conversation history as text
    for msg in conversation_parts:
        if isinstance(msg, dict) and "text" in msg:
            contents[0]["parts"].append({"text": msg["text"]})
    
    payload = {
        "contents": contents,
        "tools": [{"code_execution": {}}],
        "systemInstruction": {
            "parts": [{"text": "Use code execution to analyze images. Show your thinking by writing and running Python code to inspect the image."}]
        }
    }
    
    retry_count = 0
    max_retries = 3
    
    async with stream_semaphore:
        while retry_count <= max_retries:
            try:
                async with httpx.AsyncClient(timeout=120.0) as hpClient:
                    async with hpClient.stream("POST", stream_url, json=payload) as response:
                        if response.status_code in (429, 503):
                            if retry_count < max_retries:
                                wait_time = 2 ** retry_count
                                await asyncio.sleep(wait_time)
                                retry_count += 1
                                continue
                            else:
                                client.rotate_key()
                                stream_url = f"{GEMINI_API_STREAM_URL}?key={client.current_key}"
                                retry_count = 0
                                continue
                        
                        response.raise_for_status()
                        
                        buffered_think = ""
                        json_buffer = ""
                        depth = 0
                        
                        async for line in response.aiter_lines():
                            if not line or line == '[' or line == ']':
                                continue
                            
                            json_buffer += line + "\n"
                            
                            for char in line:
                                if char == '{':
                                    depth += 1
                                elif char == '}':
                                    depth -= 1
                            
                            if depth == 0 and json_buffer.strip():
                                try:
                                    data = json.loads(json_buffer)
                                except json.JSONDecodeError:
                                    json_buffer = ""
                                    depth = 0
                                    continue
                                
                                candidates = data.get("candidates", [])
                                if not candidates:
                                    json_buffer = ""
                                    continue
                                
                                content = candidates[0].get("content", {})
                                parts = content.get("parts", [])
                                
                                for part in parts:
                                    step = {}
                                    if "executableCode" in part:
                                        if buffered_think:
                                            yield "data: " + json.dumps({"type": "think", "content": buffered_think}) + "\n\n"
                                            await asyncio.sleep(0.05)
                                            buffered_think = ""
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
                                        buffered_think += part.get("text", "")

                                    if step:
                                        yield "data: " + json.dumps(step) + "\n\n"
                                        await asyncio.sleep(0.05)
                                
                                json_buffer = ""
                        
                        if buffered_think:
                            yield "data: " + json.dumps({"type": "think", "content": buffered_think}) + "\n\n"
                        
                        return
                        
            except Exception as e:
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    await asyncio.sleep(wait_time)
                    retry_count += 1
                    continue
                yield "data: " + json.dumps({"error": get_error_message(e)}) + "\n\n"
                return


@app.post("/api/analyze/followup")
async def followup(
    session_id: str = Form(...),
    question: str = Form(...)
):
    """Continue conversation with existing session."""
    from app.sessions import get_session
    from app.gemini_client import get_gemini_client

    image_data = await get_session(session_id)
    if not image_data:
        raise HTTPException(status_code=404, detail="Session expired. Please upload a new image.")

    client = get_gemini_client()
    try:
        answer = client.analyze(image_data, question)
        return {"answer": answer, "session_id": session_id}
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        raise HTTPException(status_code=500, detail=get_error_message(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)