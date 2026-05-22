import logging
import shutil
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("dj-generator.allin1fix")


def analyze_beats(
    file_path: str,
    stems_dir: Optional[str] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    allin1fix beat grid + structure analysis.

    When stems_dir is provided, passes pre-separated stems (from Demucs) to
    skip the internal source separation step.  stems_dir must contain:
      bass.wav, drums.wav, other.wav, vocals.wav  (htdemucs naming).

    Returns:
        {
          "beats": [float, ...],        # all beat timestamps (seconds)
          "downbeats": [float, ...],    # first beat of each bar
          "bpm_precise": float,         # integer BPM from model, cast to float
          "beat_positions": [int, ...], # 1/2/3/4 position within bar
          "segments": [{"label": str, "start": float, "end": float}, ...],
          "phrases": {
              "4bar":  [float, ...],    # downbeat times at 4-bar boundaries
              "8bar":  [float, ...],    # downbeat times at 8-bar boundaries
              "16bar": [float, ...],    # downbeat times at 16-bar boundaries
          },
          "time_signature": str,        # "4/4" (model assumes 4/4)
        }
    """
    logger.info("[%s] allin1fix starting — file=%s", job_id, Path(file_path).name)
    _update(job_id, progress=45, current_step="allin1fix")
    t0 = time.time()

    import allin1fix
    from allin1fix import create_stems_input_from_directory

    work_dir = tempfile.mkdtemp(prefix="allin1fix_work_")
    try:
        spec_dir = Path(work_dir) / "spec"
        demix_dir = Path(work_dir) / "demix"
        spec_dir.mkdir()
        demix_dir.mkdir()

        if stems_dir is not None:
            stems_input = create_stems_input_from_directory(
                stems_dir,
                identifier=job_id or Path(file_path).stem,
            )
            result = allin1fix.analyze(
                stems_input=stems_input,
                device="cpu",
                spec_dir=str(spec_dir),
                demix_dir=str(demix_dir),
                keep_byproducts=False,
                multiprocess=False,
            )
        else:
            result = allin1fix.analyze(
                paths=file_path,
                device="cpu",
                spec_dir=str(spec_dir),
                demix_dir=str(demix_dir),
                keep_byproducts=False,
                multiprocess=False,
            )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    beats = [round(float(b), 3) for b in result.beats]
    downbeats = [round(float(d), 3) for d in result.downbeats]
    beat_positions = [int(p) for p in result.beat_positions]
    segments = [
        {"label": seg.label, "start": round(float(seg.start), 3), "end": round(float(seg.end), 3)}
        for seg in result.segments
    ]

    phrases = _compute_phrases(downbeats)

    # allin1fix can return bpm=None for very short/synthetic clips.
    # Keep pipeline stable by using a safe fallback value.
    bpm_value = float(result.bpm) if result.bpm is not None else 120.0

    elapsed = time.time() - t0
    logger.info(
        "[%s] allin1fix done in %.1fs — bpm=%.2f  beats=%d  downbeats=%d  segments=%d",
        job_id, elapsed, bpm_value, len(beats), len(downbeats), len(segments),
    )
    _update(job_id, progress=60, current_step="allin1fix_done")

    return {
        "beats":           beats,
        "downbeats":       downbeats,
        "bpm_precise":     bpm_value,
        "beat_positions":  beat_positions,
        "segments":        segments,
        "phrases":         phrases,
        "time_signature":  "4/4",
    }


def _compute_phrases(downbeats: list) -> dict:
    """Derive phrase boundary times from downbeats at 4/8/16-bar intervals."""
    return {
        "4bar":  [downbeats[i] for i in range(0, len(downbeats), 4)],
        "8bar":  [downbeats[i] for i in range(0, len(downbeats), 8)],
        "16bar": [downbeats[i] for i in range(0, len(downbeats), 16)],
    }


def _update(job_id: Optional[str], **kwargs) -> None:
    if job_id is None:
        return
    try:
        from app.jobs import update_job
        update_job(job_id, **kwargs)
    except Exception as exc:
        logger.warning("[%s] Could not update job: %s", job_id, exc)
