import json
import os
from typing import Optional

import redis as redis_lib

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL = 86400  # 24 h


def _r() -> redis_lib.Redis:
    return redis_lib.from_url(REDIS_URL, decode_responses=True)


def create_job(job_id: str, file_path: str) -> dict:
    job = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0,
        "current_step": None,
        "file_path": file_path,
        "error": None,
    }
    _r().setex(f"job:{job_id}", JOB_TTL, json.dumps(job))
    return job


def get_job(job_id: str) -> Optional[dict]:
    raw = _r().get(f"job:{job_id}")
    return json.loads(raw) if raw else None


def update_job(job_id: str, **kwargs) -> Optional[dict]:
    r = _r()
    raw = r.get(f"job:{job_id}")
    if raw is None:
        return None
    job = json.loads(raw)
    job.update(kwargs)
    r.setex(f"job:{job_id}", JOB_TTL, json.dumps(job))
    return job


def save_result(job_id: str, data: dict) -> None:
    """Store full pipeline result under job:{id}:result (separate from status)."""
    _r().setex(f"job:{job_id}:result", JOB_TTL, json.dumps(data))


def get_result(job_id: str) -> Optional[dict]:
    """Retrieve full pipeline result. Returns None if not yet available."""
    raw = _r().get(f"job:{job_id}:result")
    return json.loads(raw) if raw else None
