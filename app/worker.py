"""
Celery worker — audio processing pipeline.

Tasks:
  process_audio    — full pipeline (Steps 1-7)
  reprocess_audio  — fast corrections path (skip heavy ML, apply user edits)
"""

import gc
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import numpy as np
from celery import Celery
from celery.signals import worker_ready

logger = logging.getLogger("dj-generator.worker")

BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/app/outputs"))

celery_app = Celery("worker", broker=BROKER_URL, backend=RESULT_BACKEND)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=86400,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=1,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)


@worker_ready.connect
def on_worker_ready(**kwargs):
    logger.info("Celery worker ready — broker: %s", BROKER_URL)


# ---------------------------------------------------------------------------
# Smoke-test task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="worker.add")
def add(self, x: int, y: int) -> int:
    """Smoke-test task — verifies Celery + Redis connectivity."""
    return x + y


# ---------------------------------------------------------------------------
# Faza 3.1 — Main pipeline task
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="worker.process_audio")
def process_audio(self, job_id: str, file_path: str) -> None:
    """
    Full audio processing pipeline.

    Steps:
      1  WAV conversion (ffmpeg)
      2  Demucs stem separation
      3  Essentia spectrum + waveform analysis
      4  allin1fix beat grid + structure
      5  OMAR-RQ harmony analysis
      6  Cue point generation
      7  MusicGen intro/outro generation

    Each step is wrapped in try/except — failure writes to job.error but
    pipeline continues so downstream steps can use whatever data is available.
    """
    from app.jobs import release_active_job, save_result, update_job

    update_job(job_id, status="processing", progress=0, current_step="starting")
    logger.info("[%s] pipeline starting — %s", job_id, file_path)

    job_out = OUTPUT_DIR / job_id
    stems_dir = job_out / "stems"
    job_out.mkdir(parents=True, exist_ok=True)
    stems_dir.mkdir(exist_ok=True)

    result: dict[str, Any] = {
        "job_id": job_id,
        "file_path": file_path,
        "output_dir": str(job_out),
    }

    # ── Step 1: WAV conversion ──────────────────────────────────────────────
    wav_path = str(job_out / "original.wav")
    try:
        _convert_to_wav(file_path, wav_path, job_id)
        result["wav_path"] = wav_path
    except Exception as exc:
        logger.error("[%s] WAV conversion failed: %s", job_id, exc)
        _fail(job_id, "convert", exc)
        return   # Cannot continue without WAV

    # ── Step 2: Demucs ─────────────────────────────────────────────────────
    stems: dict = {}
    allin1_stems_dir: Optional[str] = None
    try:
        from app.pipeline.demucs import separate_stems
        stems = separate_stems(wav_path, str(stems_dir), job_id=job_id)
        if stems.get("bass"):
            allin1_stems_dir = str(Path(stems["bass"]).parent)
        result["stems"] = stems
        logger.info("[%s] Demucs done — stems: %s", job_id, list(stems.keys()))
    except Exception as exc:
        logger.error("[%s] Demucs failed: %s", job_id, exc)
        update_job(job_id, error=f"Demucs failed: {exc}")
    finally:
        gc.collect()

    # ── Step 3: Essentia ───────────────────────────────────────────────────
    analysis: dict = {}
    try:
        from app.pipeline.essentia_analysis import analyze_audio
        analysis = analyze_audio(wav_path, job_id=job_id)
        result["analysis"] = _serializable(analysis)
        logger.info(
            "[%s] Essentia done — BPM=%.1f key=%s",
            job_id, analysis.get("bpm", 0), analysis.get("key", "?"),
        )
    except Exception as exc:
        logger.error("[%s] Essentia failed: %s", job_id, exc)
        update_job(job_id, error=f"Essentia failed: {exc}")

    # ── Step 4: allin1fix ──────────────────────────────────────────────────
    beats_data: dict = {}
    try:
        from app.pipeline.allin1fix import analyze_beats
        beats_data = analyze_beats(
            wav_path,
            stems_dir=allin1_stems_dir,
            job_id=job_id,
        )
        result["beats"] = _serializable(beats_data)
        logger.info(
            "[%s] allin1fix done — BPM=%.0f  beats=%d  segments=%d",
            job_id,
            beats_data.get("bpm_precise", 0),
            len(beats_data.get("beats", [])),
            len(beats_data.get("segments", [])),
        )
    except Exception as exc:
        logger.error("[%s] allin1fix failed: %s", job_id, exc)
        update_job(job_id, error=f"allin1fix failed: {exc}")
    finally:
        gc.collect()

    # ── Step 5: OMAR-RQ ────────────────────────────────────────────────────
    harmony: dict = {}
    try:
        from app.pipeline.omarrq import analyze_harmony
        harmony = analyze_harmony(
            wav_path,
            beats=beats_data.get("beats"),
            job_id=job_id,
        )
        result["harmony"] = _serializable(harmony)
        logger.info(
            "[%s] OMAR-RQ done — key=%s  camelot=%s  chords=%d",
            job_id,
            harmony.get("key", "?"),
            harmony.get("camelot", "?"),
            len(harmony.get("chord_progression", [])),
        )
    except Exception as exc:
        logger.error("[%s] OMAR-RQ failed: %s", job_id, exc)
        update_job(job_id, error=f"OMAR-RQ failed: {exc}")
    finally:
        gc.collect()

    # ── Step 6: Cue points ─────────────────────────────────────────────────
    cue_points: list = []
    try:
        from app.pipeline.cue_points import generate_cue_points
        cue_points = generate_cue_points(
            analysis=analysis,
            beats_data=beats_data,
            vocal_stem_path=stems.get("vocals"),
        )
        result["cue_points"] = cue_points
        logger.info("[%s] Cue points done — %d points", job_id, len(cue_points))
    except Exception as exc:
        logger.error("[%s] Cue points failed: %s", job_id, exc)
        update_job(job_id, error=f"Cue points failed: {exc}")

    # Merge OMAR-RQ key/mode into analysis for MusicGen prompt.
    # OMAR-RQ (24 kHz, Krumhansl-Schmuckler) gives better harmonic results
    # than Essentia for chord-conditioned generation.
    merged = {**analysis}
    if harmony:
        merged["key"]    = harmony.get("key",    analysis.get("key",    "Am"))
        merged["mode"]   = harmony.get("mode",   analysis.get("mode",   "minor"))
        merged["camelot"]= harmony.get("camelot",analysis.get("camelot","?"))

    # ── Step 7: MusicGen ───────────────────────────────────────────────────
    variations: dict = {"intros": [], "outros": []}
    try:
        from app.pipeline.musicgen import generate_variations
        variations = generate_variations(
            stems=stems,
            analysis=merged,
            beats_data=beats_data,
            output_dir=str(job_out),
            job_id=job_id,
        )
        result["variations"] = variations
        good_i = sum(1 for p in variations.get("intros", []) if p)
        good_o = sum(1 for p in variations.get("outros", []) if p)
        logger.info("[%s] MusicGen done — intros=%d/3  outros=%d/3", job_id, good_i, good_o)
    except Exception as exc:
        logger.error("[%s] MusicGen failed: %s", job_id, exc)
        update_job(job_id, error=f"MusicGen failed: {exc}")
    finally:
        gc.collect()

    # ── Finalise ───────────────────────────────────────────────────────────
    save_result(job_id, result)
    update_job(job_id, status="done", progress=100, current_step="done")
    release_active_job(job_id)
    logger.info("[%s] pipeline complete", job_id)


# ---------------------------------------------------------------------------
# Faza 3.2 — Reprocess task (fast corrections path)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, name="worker.reprocess_audio")
def reprocess_audio(self, job_id: str, corrections: dict) -> None:
    """
    Fast corrections path — skips Steps 1-6, applies user edits to existing output.

    corrections keys:
      trim_start:      float — seconds to cut from audio start
      first_beat:      float — corrected first downbeat position (updates beat offsets)
      key_shift:       int   — semitones to shift selected intro/outro (±12)
      bpm_target:      float | None — target BPM for selected intro/outro
      selected_intro:  int   — 0/1/2, which intro variant to use
      selected_outro:  int   — 0/1/2, which outro variant to use
    """
    from app.jobs import update_job, get_result, save_result

    update_job(job_id, status="processing", progress=0, current_step="reprocess_start")
    logger.info("[%s] reprocess starting — corrections=%s", job_id, corrections)

    prev = get_result(job_id)
    if not prev:
        _fail(job_id, "reprocess", RuntimeError("No existing result found — run full pipeline first"))
        return

    job_out = Path(prev.get("output_dir", str(OUTPUT_DIR / job_id)))
    reprocess_dir = job_out / "reprocess"
    reprocess_dir.mkdir(parents=True, exist_ok=True)

    result = dict(prev)
    result["corrections"] = corrections

    trim_start     = float(corrections.get("trim_start", 0.0))
    first_beat     = float(corrections.get("first_beat", 0.0))
    key_shift      = int(corrections.get("key_shift", 0))
    bpm_target     = corrections.get("bpm_target")
    selected_intro = int(corrections.get("selected_intro", 0))
    selected_outro = int(corrections.get("selected_outro", 0))

    # ── Apply trim_start to original WAV ───────────────────────────────────
    wav_path = prev.get("wav_path", "")
    if trim_start > 0.0 and wav_path and Path(wav_path).exists():
        trimmed_wav = str(reprocess_dir / "trimmed.wav")
        try:
            subprocess.run(
                ["ffmpeg", "-ss", str(trim_start), "-i", wav_path,
                 "-acodec", "pcm_s16le", "-y", trimmed_wav],
                check=True, capture_output=True, timeout=120,
            )
            result["wav_path"] = trimmed_wav
            logger.info("[%s] trim_start=%.2fs applied → %s", job_id, trim_start, trimmed_wav)
        except Exception as exc:
            logger.error("[%s] trim_start failed: %s", job_id, exc)
            update_job(job_id, error=f"trim_start failed: {exc}")

    update_job(job_id, progress=20, current_step="reprocess_selecting")

    # ── Select and correct intro variant ───────────────────────────────────
    intros = prev.get("variations", {}).get("intros", [])
    outros = prev.get("variations", {}).get("outros", [])

    selected_intro_path = _safe_path(intros, selected_intro)
    selected_outro_path = _safe_path(outros, selected_outro)

    original_bpm = float(
        prev.get("beats", {}).get("bpm_precise")
        or prev.get("analysis", {}).get("bpm")
        or 128.0
    )

    # ── Apply key_shift / bpm_target to selected variants ──────────────────
    corrected_intro = _apply_corrections(
        selected_intro_path, reprocess_dir / "intro_corrected.wav",
        key_shift, bpm_target, original_bpm, job_id,
    )
    corrected_outro = _apply_corrections(
        selected_outro_path, reprocess_dir / "outro_corrected.wav",
        key_shift, bpm_target, original_bpm, job_id,
    )

    update_job(job_id, progress=60, current_step="reprocess_corrections_done")

    # ── Update first_beat offset in beats data ─────────────────────────────
    if first_beat > 0.0 and "beats" in result:
        try:
            beats_data = result["beats"]
            orig_first = beats_data["beats"][0] if beats_data.get("beats") else 0.0
            offset = first_beat - orig_first
            if abs(offset) > 0.005:
                beats_data["beats"]     = [round(b + offset, 3) for b in beats_data.get("beats", [])]
                beats_data["downbeats"] = [round(d + offset, 3) for d in beats_data.get("downbeats", [])]
                result["beats"] = beats_data
                logger.info("[%s] first_beat offset %.3fs applied to beat grid", job_id, offset)
        except Exception as exc:
            logger.warning("[%s] beat offset failed: %s", job_id, exc)

    # ── Save corrected result ──────────────────────────────────────────────
    result["reprocess"] = {
        "selected_intro_path": corrected_intro,
        "selected_outro_path": corrected_outro,
        "selected_intro_index": selected_intro,
        "selected_outro_index": selected_outro,
        "trim_start": trim_start,
        "key_shift": key_shift,
        "bpm_target": bpm_target,
        "first_beat": first_beat,
    }

    save_result(job_id, result)
    update_job(job_id, status="done", progress=100, current_step="reprocess_done")
    logger.info("[%s] reprocess complete", job_id)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _convert_to_wav(input_path: str, output_path: str, job_id: str) -> None:
    """
    Convert any audio format to 44100 Hz stereo 16-bit PCM WAV using ffmpeg.
    Stereo is required by allin1fix (htdemucs internally expects 2 channels).
    """
    from app.jobs import update_job
    update_job(job_id, progress=1, current_step="convert")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-i", input_path,
            "-ar", "44100",       # sample rate
            "-ac", "2",           # force stereo
            "-acodec", "pcm_s16le",
            "-y", output_path,
        ],
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={result.returncode}): {result.stderr.decode()[-500:]}"
        )

    update_job(job_id, progress=5, current_step="convert_done")
    logger.info("[%s] WAV conversion done → %s", job_id, output_path)


def _apply_corrections(
    src_path: Optional[str],
    dst_path: Path,
    key_shift: int,
    bpm_target: Optional[float],
    original_bpm: float,
    job_id: str,
) -> Optional[str]:
    """Apply pitch shift and/or tempo stretch to an audio file."""
    if not src_path or not Path(src_path).exists():
        logger.warning("[%s] Source not found for corrections: %s", job_id, src_path)
        return src_path

    from app.pipeline.rubberband import shift_pitch, stretch_tempo

    current = src_path
    try:
        if key_shift != 0:
            shifted = str(dst_path.parent / f"{dst_path.stem}_shift.wav")
            current = shift_pitch(current, key_shift, shifted)

        if bpm_target and abs(bpm_target - original_bpm) > 0.1:
            stretched = str(dst_path)
            current = stretch_tempo(current, bpm_target, original_bpm, stretched)
        elif key_shift != 0:
            # Rename shifted file to final dst if no tempo change
            import shutil
            shutil.move(current, str(dst_path))
            current = str(dst_path)
    except Exception as exc:
        logger.error("[%s] Correction failed for %s: %s", job_id, src_path, exc)
        return src_path

    return current


def _safe_path(paths: list, index: int) -> Optional[str]:
    """Return paths[index] if it exists and is a valid file, else first valid."""
    if 0 <= index < len(paths) and paths[index] and Path(paths[index]).exists():
        return paths[index]
    # Fallback: first valid path
    for p in paths:
        if p and Path(p).exists():
            logger.warning("Selected index invalid, falling back to first valid variant")
            return p
    return None


def _serializable(obj: Any) -> Any:
    """Recursively convert numpy/torch types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _fail(job_id: str, step: str, exc: Exception) -> None:
    """Mark job as failed with error message."""
    from app.jobs import release_active_job, update_job
    msg = f"{step} failed: {exc}"
    logger.error("[%s] %s", job_id, msg)
    update_job(job_id, status="failed", current_step=step, error=msg)
    release_active_job(job_id)
