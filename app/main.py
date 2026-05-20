import logging
import os
import uuid
from pathlib import Path

import redis as redis_client
import filetype
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.jobs import create_job, get_job, get_result
from app.models.schemas import JobResultResponse, JobStatusResponse, ReprocessRequest, UploadResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("dj-generator")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))
_allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000")
ALLOWED_ORIGINS_LIST = [o.strip() for o in _allowed_origins_env.split(",") if o.strip()]
MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB

# Allowed file types for the download endpoint (prevents path traversal)
_AUDIO_FILES = {
    "intro_0", "intro_1", "intro_2",
    "outro_0", "outro_1", "outro_2",
    "original",
}

ALLOWED_MIME_TYPES = {
    "audio/mpeg",   # MP3
    "audio/x-wav",  # WAV
    "audio/wav",
    "audio/x-flac", # FLAC
    "audio/flac",
    "audio/aac",    # AAC
    "audio/x-aac",
}

app = FastAPI(
    title="DJ Intro/Outro Generator",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_LIST,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": "Not found", "path": str(request.url.path)},
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Internal error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})


@app.get("/health")
async def health() -> dict:
    redis_ok = False
    try:
        r = redis_client.from_url(REDIS_URL, socket_connect_timeout=2)
        redis_ok = r.ping()
    except Exception as e:
        logger.warning("Redis health check failed: %s", e)

    return {"status": "ok", "redis": "ok" if redis_ok else "unavailable"}


@app.post("/api/upload", response_model=UploadResponse, status_code=202)
async def upload_audio(file: UploadFile) -> UploadResponse:
    # --- read file in one shot (max 100 MB + 1 byte to detect oversize) ---
    raw = await file.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 100 MB.")

    # --- server-side MIME detection from magic bytes ---
    kind = filetype.guess(raw[:512])
    mime = kind.mime if kind else None
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{mime}'. Accepted: MP3, WAV, FLAC, AAC.",
        )

    # --- derive safe extension from detected type, not from filename ---
    ext_map = {
        "audio/mpeg": ".mp3",
        "audio/x-wav": ".wav", "audio/wav": ".wav",
        "audio/x-flac": ".flac", "audio/flac": ".flac",
        "audio/aac": ".aac", "audio/x-aac": ".aac",
    }
    ext = ext_map[mime]

    # --- save with UUID name ---
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    dest = UPLOAD_DIR / f"{job_id}{ext}"
    dest.write_bytes(raw)

    # --- create job record in Redis ---
    create_job(job_id, str(dest))
    logger.info("Job %s queued — file: %s (%d bytes)", job_id, dest.name, len(raw))

    # --- dispatch Celery task (imported lazily to avoid circular import) ---
    from app.worker import process_audio
    process_audio.delay(job_id, str(dest))

    return UploadResponse(job_id=job_id, status="queued")


@app.get("/api/status/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return JobStatusResponse(**job)


@app.get("/api/result/{job_id}", response_model=JobResultResponse)
async def job_result(job_id: str) -> JobResultResponse:
    """Full pipeline result — available only after status=done."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.get("status") not in ("done",):
        raise HTTPException(
            status_code=409,
            detail=f"Job not finished yet (status={job.get('status')}).",
        )
    data = get_result(job_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Result data not found.")
    return JobResultResponse(
        job_id=job_id,
        status=job.get("status", "done"),
        analysis=data.get("analysis"),
        beats=data.get("beats"),
        harmony=data.get("harmony"),
        cue_points=data.get("cue_points"),
        variations=data.get("variations"),
        error=job.get("error"),
    )


@app.post("/api/reprocess/{job_id}", response_model=JobStatusResponse, status_code=202)
async def reprocess(job_id: str, body: ReprocessRequest) -> JobStatusResponse:
    """
    Apply user corrections to existing job without re-running heavy ML steps.

    Applies:
      - trim_start: silence removal from audio start
      - first_beat: realign beat grid
      - key_shift:  pitch shift selected intro/outro (±12 semitones)
      - bpm_target: tempo stretch selected intro/outro
      - selected_intro/outro: pick variant 0/1/2
    """
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    if job.get("status") not in ("done", "failed"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot reprocess job with status '{job.get('status')}'.",
        )

    from app.worker import reprocess_audio
    reprocess_audio.delay(job_id, body.model_dump())
    logger.info("Job %s queued for reprocess — corrections: %s", job_id, body.model_dump())

    from app.jobs import update_job
    updated = update_job(job_id, status="processing", progress=0, current_step="reprocess_queued")
    return JobStatusResponse(**updated)


@app.get("/api/download/{job_id}/{file_type}")
async def download_audio(job_id: str, file_type: str) -> FileResponse:
    """Stream a generated audio file (intro_0–2, outro_0–2, original)."""
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format.")

    if file_type not in _AUDIO_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown file type '{file_type}'. Allowed: {sorted(_AUDIO_FILES)}",
        )

    file_path = OUTPUT_DIR / job_id / f"{file_type}.wav"
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Audio file '{file_type}' not found for this job.")

    return FileResponse(
        path=file_path,
        media_type="audio/wav",
        filename=f"{file_type}.wav",
        headers={"Accept-Ranges": "bytes"},
    )
