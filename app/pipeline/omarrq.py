"""
OMAR-RQ harmony analysis — Step 4 of the audio pipeline.

Model: mtg-upf/omar-rq-multifeature-25hz-fsq
  - Raw audio input at 24 kHz, mono
  - 25 Hz output frame rate (40 ms frames)
  - Layer 6 embeddings best for tonal/pitch tasks

Architecture:
  1. Load audio → resample to 24 kHz mono
  2. Extract OMAR-RQ embeddings (actual model inference)
  3. Compute FFT-based chromagram at 25 Hz (matches model frame rate)
  4. Krumhansl-Schmuckler key detection on mean chromagram
  5. Template-matching chord detection (beat-sync when beats supplied)
  6. Return structured harmony dict; OMAR-RQ model freed after use

Fallback: if OMAR-RQ model unavailable (first download, OOM, etc.),
  chromagram analysis still runs and returns valid harmony data.
"""

import gc
import logging
import time
from typing import Optional

import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T

logger = logging.getLogger("dj-generator.omarrq")

_MODEL_ID = "mtg-upf/omar-rq-multifeature-25hz-fsq"
_SAMPLE_RATE = 24_000       # OMAR-RQ multifeature native sample rate
_HOP = _SAMPLE_RATE // 25   # 960 samples → 25 Hz frame rate
_N_FFT = 8192               # ~2.93 Hz bin resolution at 24 kHz
_LAYER = 6                  # Best layer for tonal probing (per SSL-music literature)

# ---------------------------------------------------------------------------
# Harmonic constants
# ---------------------------------------------------------------------------

_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Krumhansl-Schmuckler pitch-class salience profiles (from Krumhansl 1990)
_KS_MAJOR = np.array(
    [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88],
    dtype=np.float32,
)
_KS_MINOR = np.array(
    [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17],
    dtype=np.float32,
)

_CAMELOT: dict[tuple[str, str], str] = {
    ("C", "major"): "8B",  ("G", "major"): "9B",  ("D", "major"): "10B",
    ("A", "major"): "11B", ("E", "major"): "12B", ("B", "major"): "1B",
    ("F#", "major"): "2B", ("C#", "major"): "3B", ("G#", "major"): "4B",
    ("D#", "major"): "5B", ("A#", "major"): "6B", ("F", "major"): "7B",
    ("A", "minor"): "8A",  ("E", "minor"): "9A",  ("B", "minor"): "10A",
    ("F#", "minor"): "11A",("C#", "minor"): "12A",("G#", "minor"): "1A",
    ("D#", "minor"): "2A", ("A#", "minor"): "3A", ("F", "minor"): "4A",
    ("C", "minor"): "5A",  ("G", "minor"): "6A",  ("D", "minor"): "7A",
}


def _build_chord_templates() -> dict[str, np.ndarray]:
    """
    Normalised HPCP templates for 24 triads (12 major + 12 minor).
    Major: root (1.0) + M3 +4 st (0.5) + P5 +7 st (0.8)
    Minor: root (1.0) + m3 +3 st (0.5) + P5 +7 st (0.8)
    Weights reflect typical HPCP saliency ordering (root > 5th > 3rd).
    """
    templates: dict[str, np.ndarray] = {}
    for root_idx, root in enumerate(_NOTES):
        for intervals, label_suffix in [([0, 4, 7], ""), ([0, 3, 7], "m")]:
            weights = [1.0, 0.5, 0.8]
            hpcp = np.zeros(12, dtype=np.float32)
            for w, st in zip(weights, intervals):
                hpcp[(root_idx + st) % 12] += w
            hpcp /= np.linalg.norm(hpcp)
            templates[root + label_suffix] = hpcp
    return templates


_CHORD_TEMPLATES = _build_chord_templates()

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_24k_mono(file_path: str) -> torch.Tensor:
    """Return (1, samples) float32 tensor at 24 kHz."""
    waveform, sr = torchaudio.load(file_path)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != _SAMPLE_RATE:
        waveform = T.Resample(orig_freq=sr, new_freq=_SAMPLE_RATE)(waveform)
    return waveform


def _chromagram(waveform: torch.Tensor) -> np.ndarray:
    """
    FFT-based chromagram at 25 Hz, aligned with OMAR-RQ output rate.

    Steps:
      - Power spectrogram with n_fft=8192, hop=960 (40 ms)
      - Map each FFT bin to MIDI pitch class via log-frequency formula
      - Scatter-add spectral energy into 12 chroma bins
      - L2-normalise each frame

    Returns (12, T) float32 array.
    """
    spec = T.Spectrogram(n_fft=_N_FFT, hop_length=_HOP, power=2.0)(waveform[0])
    # spec: (n_fft//2 + 1, T)  — shape e.g. (4097, T)

    # Frequency of each FFT bin: f_k = k * sr / n_fft
    bin_freqs = torch.arange(spec.shape[0], dtype=torch.float32) * _SAMPLE_RATE / _N_FFT

    # Restrict to piano range A0 (27.5 Hz) – C8 (4186 Hz)
    valid_mask = (bin_freqs >= 27.5) & (bin_freqs <= 4186.0)
    valid_idx = valid_mask.nonzero(as_tuple=True)[0]  # (V,)

    # MIDI pitch class for each valid bin: pc = round(12·log2(f/A4) + 69) mod 12
    midi = 12.0 * torch.log2(bin_freqs[valid_idx] / 440.0) + 69.0
    pcs = torch.round(midi).long() % 12  # (V,)

    # Scatter energy into chroma using vectorised scatter_add
    valid_spec = spec[valid_idx]  # (V, T)
    chroma = torch.zeros(12, spec.shape[1])
    # index: (V, T) — each row holds the target pitch class repeated T times
    index = pcs.unsqueeze(1).expand(-1, spec.shape[1])
    chroma.scatter_add_(0, index, valid_spec)

    chroma_np = chroma.numpy().astype(np.float32)
    norms = np.linalg.norm(chroma_np, axis=0, keepdims=True)
    norms[norms < 1e-8] = 1.0
    return chroma_np / norms


def _detect_key(chroma: np.ndarray) -> tuple[str, str, float]:
    """
    Krumhansl-Schmuckler key detection on mean chromagram.
    Returns (key_note, mode, confidence ∈ [0, 1]).
    """
    mean_chroma = chroma.mean(axis=1)  # (12,)
    best_corr = -np.inf
    best_note, best_mode = "C", "major"

    for tonic in range(12):
        for mode, profile in [("major", _KS_MAJOR), ("minor", _KS_MINOR)]:
            corr = float(np.corrcoef(mean_chroma, np.roll(profile, tonic))[0, 1])
            if corr > best_corr:
                best_corr = corr
                best_note = _NOTES[tonic]
                best_mode = mode

    # Map Pearson r ∈ [-1, 1] → confidence ∈ [0, 1]
    confidence = round(max(0.0, min(1.0, (best_corr + 1.0) / 2.0)), 3)
    return best_note, best_mode, confidence


def _match_chord(hpcp: np.ndarray) -> str:
    """Cosine nearest-neighbour chord label for an HPCP vector."""
    norm = float(np.linalg.norm(hpcp))
    if norm < 1e-8:
        return "N"
    hpcp_unit = hpcp / norm
    return max(_CHORD_TEMPLATES, key=lambda c: float(np.dot(hpcp_unit, _CHORD_TEMPLATES[c])))


def _chord_sequence(
    chroma: np.ndarray,
    beats: Optional[list] = None,
) -> list[str]:
    """
    One chord label per beat interval (beat-sync) or per 2-second window.
    Returns list of strings like ["Am", "F", "C", "G"].
    """
    if beats and len(beats) >= 2:
        chords: list[str] = []
        n_frames = chroma.shape[1]
        for i in range(len(beats) - 1):
            f0 = max(0, int(beats[i] * 25))           # 25 Hz → frame index
            f1 = min(n_frames, int(beats[i + 1] * 25))
            f1 = max(f0 + 1, f1)
            chords.append(_match_chord(chroma[:, f0:f1].mean(axis=1)))
        return chords

    # Fallback: 2-second windows (50 frames at 25 Hz)
    step = 50
    return [
        _match_chord(chroma[:, s: min(s + step, chroma.shape[1])].mean(axis=1))
        for s in range(0, chroma.shape[1], step)
    ]

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_harmony(
    file_path: str,
    beats: Optional[list] = None,
    job_id: Optional[str] = None,
) -> dict:
    """
    OMAR-RQ Step 4: harmony analysis — key, mode, chords, pitch, camelot.

    Args:
        file_path: Path to audio (any format; resampled to 24 kHz mono internally).
        beats:     Beat timestamps (seconds) from allin1fix for beat-sync chords.
                   If None, falls back to 2-second chord windows.
        job_id:    Celery job ID for Redis progress updates.

    Returns:
        {
          "key":              str,         # e.g. "Am" or "C"
          "key_root":         str,         # e.g. "A" or "C"
          "mode":             str,         # "major" or "minor"
          "key_confidence":   float,       # 0.0 – 1.0
          "camelot":          str,         # e.g. "8A"
          "chord_progression": [str, ...], # one per beat (or per 2 s)
          "pitch_midi":       int,         # MIDI tonic note (C4 = 60)
          "embeddings_shape": [T, C] | None,  # OMAR-RQ embedding dims
          "duration_analyzed": float,      # seconds of audio processed
        }
    """
    t0 = time.time()
    _update(job_id, progress=60, current_step="omar_rq")
    logger.info("[%s] OMAR-RQ analysis starting — %s", job_id, file_path)

    # Step 1: Load audio at OMAR-RQ native rate
    waveform = _load_24k_mono(file_path)  # (1, samples)

    # Step 2: Extract OMAR-RQ embeddings
    # Embeddings encode pitch/tonal structure at 25 Hz; cleaned from memory after use.
    embeddings_shape: Optional[list] = None
    try:
        from omar_rq import get_model
        model = get_model(model_id=_MODEL_ID, device="cpu")
        with torch.no_grad():
            emb = model.extract_embeddings(waveform, layers=[_LAYER])
        # emb: (L=1, B=1, T, C)
        embeddings_shape = list(emb.shape[2:])  # [T, C]
        logger.info("[%s] OMAR-RQ embeddings extracted: T=%d C=%d", job_id, *embeddings_shape)
        del model, emb
        gc.collect()
    except Exception as exc:
        logger.warning("[%s] OMAR-RQ model unavailable (%s) — chromagram analysis continues", job_id, exc)

    _update(job_id, progress=66, current_step="omar_rq_chromagram")

    # Step 3: FFT chromagram at 25 Hz (same frame rate as OMAR-RQ embeddings)
    chroma = _chromagram(waveform)  # (12, T)

    # Step 4: Key detection via Krumhansl-Schmuckler
    key_note, mode, key_confidence = _detect_key(chroma)

    # Step 5: Beat-synchronised chord progression
    chord_progression = _chord_sequence(chroma, beats=beats)

    # Step 6: Derive remaining fields
    pitch_midi = 60 + _NOTES.index(key_note)  # tonic as MIDI (C4 = 60)
    camelot = _CAMELOT.get((key_note, mode), "?")
    key_str = f"{key_note}{'m' if mode == 'minor' else ''}"

    elapsed = time.time() - t0
    logger.info(
        "[%s] OMAR-RQ done in %.1fs — key=%s  mode=%s  camelot=%s  chords=%d",
        job_id, elapsed, key_note, mode, camelot, len(chord_progression),
    )
    _update(job_id, progress=72, current_step="omar_rq_done")

    return {
        "key": key_str,
        "key_root": key_note,
        "mode": mode,
        "key_confidence": key_confidence,
        "camelot": camelot,
        "chord_progression": chord_progression,
        "pitch_midi": pitch_midi,
        "embeddings_shape": embeddings_shape,
        "duration_analyzed": round(waveform.shape[1] / _SAMPLE_RATE, 2),
    }


def _update(job_id: Optional[str], **kwargs) -> None:
    if job_id is None:
        return
    try:
        from app.jobs import update_job
        update_job(job_id, **kwargs)
    except Exception as exc:
        logger.warning("[%s] Job update failed: %s", job_id, exc)
