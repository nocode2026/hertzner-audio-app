import json
import os
from typing import Optional

import redis as redis_lib

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JOB_TTL = 86400  # 24 h
ACTIVE_JOB_KEY = "job:active"
ACTIVE_JOB_TTL = 6 * 3600  # safety TTL for stale locks


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


def get_active_job_id() -> Optional[str]:
    """Return currently active job id if lock is held."""
    return _r().get(ACTIVE_JOB_KEY)


def acquire_active_job(job_id: str) -> tuple[bool, Optional[str]]:
    """
    Acquire single active-job lock.

    Returns:
      (True, None) on successful acquisition
      (False, active_job_id) when another active job is running/queued
    """
    r = _r()
    if r.set(ACTIVE_JOB_KEY, job_id, nx=True, ex=ACTIVE_JOB_TTL):
        return True, None

    active_job_id = r.get(ACTIVE_JOB_KEY)
    if not active_job_id:
        # Lock disappeared between calls; retry once.
        if r.set(ACTIVE_JOB_KEY, job_id, nx=True, ex=ACTIVE_JOB_TTL):
            return True, None
        active_job_id = r.get(ACTIVE_JOB_KEY)

    if not active_job_id:
        return False, None

    raw = r.get(f"job:{active_job_id}")
    if raw is None:
        # Orphaned lock (status key expired). Clear and retry once.
        r.delete(ACTIVE_JOB_KEY)
        if r.set(ACTIVE_JOB_KEY, job_id, nx=True, ex=ACTIVE_JOB_TTL):
            return True, None
        return False, r.get(ACTIVE_JOB_KEY)

    job = json.loads(raw)
    if job.get("status") in ("done", "failed"):
        # Stale lock after terminal status; clear and retry once.
        r.delete(ACTIVE_JOB_KEY)
        if r.set(ACTIVE_JOB_KEY, job_id, nx=True, ex=ACTIVE_JOB_TTL):
            return True, None
        return False, r.get(ACTIVE_JOB_KEY)

    return False, active_job_id


def release_active_job(job_id: str) -> None:
    """Release active-job lock only if it belongs to this job id."""
    r = _r()
    if r.get(ACTIVE_JOB_KEY) == job_id:
        r.delete(ACTIVE_JOB_KEY)
