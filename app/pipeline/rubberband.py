"""
pyrubberband pitch shifting and time stretching — Step 8 of the pipeline.

Wraps pyrubberband (which calls the system rubberband-cli binary) for:
  - shift_pitch:    change key without changing tempo
  - stretch_tempo:  change BPM without changing pitch

Safe ranges (per MASTER_CONTEXT — beyond these, artifacts may appear):
  ±2 semitones for pitch shift
  ±10% for tempo stretch

Operations outside the safe range log a WARNING but still execute.
Both functions are no-ops (file copy) when the adjustment is zero.

Requires: rubberband-cli installed (apt install rubberband-cli — in Dockerfile).
"""

import logging
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torchaudio

logger = logging.getLogger("dj-generator.rubberband")

_SAFE_SEMITONES = 2.0    # |semitones| > this → warning
_SAFE_BPM_PCT = 10.0     # |bpm change %| > this → warning


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def shift_pitch(
    file_path: str,
    semitones: float,
    output_path: str,
) -> str:
    """
    Pitch-shift audio by N semitones without changing tempo.

    Args:
        file_path:   Input audio file (any format supported by torchaudio).
        semitones:   Semitones to shift (+= up, -= down).
                     Safe range: ±2 st. Beyond ±2 st a warning is logged.
        output_path: Output WAV path (created if parent does not exist).

    Returns:
        output_path (str)
    """
    semitones = float(semitones)

    if abs(semitones) > _SAFE_SEMITONES:
        logger.warning(
            "Pitch shift %.1f st exceeds safe range ±%.0f st — artefacts possible",
            semitones, _SAFE_SEMITONES,
        )

    if abs(semitones) < 1e-4:
        _copy(file_path, output_path)
        return output_path

    import pyrubberband as pyrb

    audio_np, sr = _load(file_path)           # (samples,) or (samples, ch), float64
    shifted = pyrb.pitch_shift(audio_np, sr, n_steps=semitones)
    _save(shifted, sr, output_path)

    logger.info("shift_pitch %.2f st: %s → %s", semitones, file_path, output_path)
    return output_path


def stretch_tempo(
    file_path: str,
    target_bpm: float,
    original_bpm: float,
    output_path: str,
) -> str:
    """
    Time-stretch audio to target BPM without changing pitch.

    Args:
        file_path:    Input audio file (any format).
        target_bpm:   Target beats per minute.
        original_bpm: Original beats per minute.
        output_path:  Output WAV path.

    Returns:
        output_path (str)

    Raises:
        ValueError: if either BPM value is non-positive.
    """
    target_bpm = float(target_bpm)
    original_bpm = float(original_bpm)

    if target_bpm <= 0 or original_bpm <= 0:
        raise ValueError(
            f"BPM values must be positive; got original={original_bpm}, target={target_bpm}"
        )

    rate = target_bpm / original_bpm          # >1 = speed up, <1 = slow down
    change_pct = abs(rate - 1.0) * 100.0

    if change_pct > _SAFE_BPM_PCT:
        logger.warning(
            "Tempo stretch %.1f→%.1f BPM (%.1f%%) exceeds safe range ±%.0f%% — artefacts possible",
            original_bpm, target_bpm, change_pct, _SAFE_BPM_PCT,
        )

    if abs(rate - 1.0) < 1e-4:
        _copy(file_path, output_path)
        return output_path

    import pyrubberband as pyrb

    audio_np, sr = _load(file_path)
    stretched = pyrb.time_stretch(audio_np, sr, rate=rate)
    _save(stretched, sr, output_path)

    logger.info(
        "stretch_tempo %.1f→%.1f BPM (×%.3f): %s → %s",
        original_bpm, target_bpm, rate, file_path, output_path,
    )
    return output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load(file_path: str) -> tuple[np.ndarray, int]:
    """
    Load audio via torchaudio → numpy float64.

    pyrubberband expects:
      mono:   (samples,)
      stereo: (samples, 2)  — NOT (2, samples)
    """
    waveform, sr = torchaudio.load(file_path)   # (channels, samples) float32
    audio = waveform.numpy().T.astype(np.float64)  # (samples, channels) or (samples, 1)
    if waveform.shape[0] == 1:
        audio = audio[:, 0]                     # (samples,) for mono
    return audio, sr


def _save(audio_np: np.ndarray, sr: int, output_path: str) -> None:
    """
    Save numpy audio array (pyrubberband output) to WAV via torchaudio.
    Accepts (samples,) mono or (samples, channels) stereo.
    """
    if audio_np.ndim == 1:
        tensor = torch.from_numpy(audio_np.astype(np.float32)).unsqueeze(0)
    else:
        tensor = torch.from_numpy(audio_np.T.astype(np.float32))  # (channels, samples)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    torchaudio.save(output_path, tensor, sr)


def _copy(src: str, dst: str) -> None:
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
