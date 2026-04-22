import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dataclasses import asdict
from dotenv import load_dotenv

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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)