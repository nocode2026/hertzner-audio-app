import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("dj-generator.demucs")

MODEL = "htdemucs"
TIMEOUT_SECONDS = 30 * 60  # 30 min


def separate_stems(
    input_path: str,
    output_dir: str,
    job_id: Optional[str] = None,
) -> dict:
    """
    Run htdemucs on input_path, return paths to the 4 stem files.

    Returns:
        {"vocals": str, "drums": str, "bass": str, "melody": str}
        where "melody" maps to htdemucs "other" stem.

    Raises:
        RuntimeError on timeout, non-zero exit, or missing output files.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[%s] Demucs starting — model=%s  file=%s", job_id, MODEL, input_path.name)
    _update(job_id, progress=10, current_step="demucs")

    start = time.time()
    cmd = [
        "python", "-m", "demucs",
        "-n", MODEL,
        "-o", str(output_dir),
        str(input_path),
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Demucs timed out after {TIMEOUT_SECONDS // 60} minutes on {input_path.name}"
        )

    if proc.returncode != 0:
        tail = proc.stderr[-600:] if proc.stderr else proc.stdout[-600:]
        raise RuntimeError(f"Demucs exited {proc.returncode}: {tail}")

    # htdemucs writes to: output_dir/htdemucs/<track_stem>/{vocals,drums,bass,other}.wav
    stems_dir = output_dir / MODEL / input_path.stem
    stems = {
        "vocals": str(stems_dir / "vocals.wav"),
        "drums":  str(stems_dir / "drums.wav"),
        "bass":   str(stems_dir / "bass.wav"),
        "melody": str(stems_dir / "other.wav"),   # htdemucs calls this "other"
    }

    for name, path in stems.items():
        p = Path(path)
        if not p.exists():
            raise RuntimeError(f"Demucs output missing: {name} → {path}")
        if p.stat().st_size == 0:
            raise RuntimeError(f"Demucs output empty: {name} → {path}")

    elapsed = time.time() - start
    logger.info("[%s] Demucs done in %.1fs — stems in %s", job_id, elapsed, stems_dir)
    _update(job_id, progress=25, current_step="demucs_done")

    return stems


def _update(job_id: Optional[str], **kwargs) -> None:
    if job_id is None:
        return
    try:
        from app.jobs import update_job
        update_job(job_id, **kwargs)
    except Exception as e:
        logger.warning("[%s] Could not update job status: %s", job_id, e)
