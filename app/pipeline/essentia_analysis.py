import logging
import time
from pathlib import Path
from typing import Optional

import essentia.standard as es
import numpy as np

logger = logging.getLogger("dj-generator.essentia")

SAMPLE_RATE = 44100

# Camelot wheel: (root, mode) → position
_CAMELOT: dict[tuple, str] = {
    # Major (B suffix)
    ("B", "major"): "1B",
    ("F#", "major"): "2B",  ("Gb", "major"): "2B",
    ("C#", "major"): "3B",  ("Db", "major"): "3B",
    ("Ab", "major"): "4B",  ("G#", "major"): "4B",
    ("Eb", "major"): "5B",  ("D#", "major"): "5B",
    ("Bb", "major"): "6B",  ("A#", "major"): "6B",
    ("F",  "major"): "7B",
    ("C",  "major"): "8B",
    ("G",  "major"): "9B",
    ("D",  "major"): "10B",
    ("A",  "major"): "11B",
    ("E",  "major"): "12B",
    # Minor (A suffix)
    ("Ab", "minor"): "1A",  ("G#", "minor"): "1A",
    ("Eb", "minor"): "2A",  ("D#", "minor"): "2A",
    ("Bb", "minor"): "3A",  ("A#", "minor"): "3A",
    ("F",  "minor"): "4A",
    ("C",  "minor"): "5A",
    ("G",  "minor"): "6A",
    ("D",  "minor"): "7A",
    ("A",  "minor"): "8A",
    ("E",  "minor"): "9A",
    ("B",  "minor"): "10A",
    ("F#", "minor"): "11A", ("Gb", "minor"): "11A",
    ("C#", "minor"): "12A", ("Db", "minor"): "12A",
}

# Essentia uses flats; normalise to the display convention expected by the front-end
_KEY_NORM = {"Db": "C#", "D#": "Eb", "Gb": "F#", "G#": "Ab", "A#": "Bb"}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_audio(file_path: str, job_id: Optional[str] = None) -> dict:
    """
    Full Essentia analysis of an audio file.

    Returns a dict with rhythm, harmony, structure, energy, spectral,
    waveform-RGB, and metadata fields — as specified in BUILD_PLAN step 2.3.
    """
    path = Path(file_path)
    logger.info("[%s] Essentia starting — file=%s", job_id, path.name)
    _update(job_id, progress=25, current_step="essentia")
    t0 = time.time()

    audio = es.MonoLoader(filename=str(path), sampleRate=SAMPLE_RATE)()
    duration = len(audio) / SAMPLE_RATE

    # --- rhythm ---
    bpm, beats, bpm_confidence = _rhythm(audio)
    tempo_stability = _tempo_stability(beats)

    # --- harmony ---
    raw_key, mode, key_confidence = _key(audio)
    norm_key = _KEY_NORM.get(raw_key, raw_key)
    camelot = _CAMELOT.get((norm_key, mode), _CAMELOT.get((raw_key, mode), "?"))
    key_display = norm_key + ("m" if mode == "minor" else "")

    chord_progression = _chords(audio)

    # --- structure ---
    segments = _segments(duration, bpm)

    # --- energy ---
    energy_curve = _energy_curve(audio)
    lufs = _lufs(audio)
    dynamic_range = _dynamic_range(audio)

    # --- spectral ---
    sp = _spectral(audio)
    stereo_width = _stereo_width(str(path))

    # --- waveform RGB (for Pixi.js) ---
    waveform = _waveform_rgb(audio)

    elapsed = time.time() - t0
    logger.info(
        "[%s] Essentia done in %.1fs — bpm=%.2f  key=%s  camelot=%s",
        job_id, elapsed, bpm, key_display, camelot,
    )
    _update(job_id, progress=45, current_step="essentia_done")

    return {
        # rhythm
        "bpm":             bpm,
        "bpm_confidence":  bpm_confidence,
        "beat_positions":  beats,
        "tempo_stability": tempo_stability,
        # harmony
        "key":              key_display,
        "mode":             mode,
        "key_confidence":   key_confidence,
        "camelot":          camelot,
        "chord_progression": chord_progression,
        # structure
        "segments": segments,
        # energy
        "energy_curve":   energy_curve,
        "lufs":           lufs,
        "dynamic_range":  dynamic_range,
        # spectral
        "spectral_centroid": sp["centroid"],
        "brightness":        sp["brightness"],
        "bass_intensity":    sp["bass_intensity"],
        "stereo_width":      stereo_width,
        # waveform
        "waveform": waveform,
        # metadata
        "duration":    round(duration, 3),
        "sample_rate": SAMPLE_RATE,
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _rhythm(audio: np.ndarray) -> tuple:
    try:
        bpm, ticks, conf, _, _ = es.RhythmExtractor2013(method="multifeature")(audio)
        return (
            round(float(bpm), 2),
            [round(float(t), 3) for t in ticks],
            round(float(conf), 3),
        )
    except Exception as exc:
        logger.warning("BPM extraction failed: %s", exc)
        return 120.0, [], 0.0


def _tempo_stability(beats: list) -> float:
    if len(beats) < 3:
        return 0.5
    intervals = np.diff(beats)
    mean = float(np.mean(intervals))
    if mean < 1e-6:
        return 0.5
    # Coefficient of variation → invert for "stability"
    return round(float(np.clip(1.0 - np.std(intervals) / mean, 0.0, 1.0)), 3)


def _key(audio: np.ndarray) -> tuple:
    try:
        key, scale, strength = es.KeyExtractor()(audio)
        return str(key), str(scale), round(float(strength), 3)
    except Exception as exc:
        logger.warning("Key extraction failed: %s", exc)
        return "C", "major", 0.0


def _chords(audio: np.ndarray) -> list:
    """Per-bar chord labels via HPCP → ChordsDetection pipeline."""
    try:
        frame_size = 4096
        hop_size   = 2048
        hpcp_algo  = es.HPCP()
        win_algo   = es.Windowing(type="hann")
        spec_algo  = es.Spectrum(size=frame_size)
        peaks_algo = es.SpectralPeaks()

        hpcps = []
        for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size):
            spectrum = spec_algo(win_algo(frame))
            freqs, mags = peaks_algo(spectrum)
            hpcps.append(hpcp_algo(freqs, mags))

        if len(hpcps) < 2:
            return []

        chords, _ = es.ChordsDetection()(np.array(hpcps))

        # One chord per ~4 seconds
        frames_per_4s = max(1, int(4 * SAMPLE_RATE / hop_size))
        return [str(chords[i]) for i in range(0, len(chords), frames_per_4s)]
    except Exception as exc:
        logger.warning("Chord detection failed: %s", exc)
        return []


def _segments(duration: float, bpm: float) -> list:
    """
    Heuristic 3-part structure used until allin1fix provides better labels (Phase 2.4).
    Guaranteed to return at least one segment.
    """
    bpm = bpm if bpm > 0 else 120.0
    bar_dur = 4 * 60.0 / bpm

    intro_end    = round(min(0.12 * duration, 32.0), 2)
    outro_start  = round(max(0.88 * duration, duration - 32.0), 2)

    def bar_count(a: float, b: float) -> int:
        return max(1, round((b - a) / bar_dur))

    segs = []
    if intro_end > 0:
        segs.append({"type": "intro",  "start": 0.0,        "end": intro_end,   "bars": bar_count(0,          intro_end)})
    if intro_end < outro_start:
        segs.append({"type": "drop",   "start": intro_end,  "end": outro_start, "bars": bar_count(intro_end,  outro_start)})
    if outro_start < duration:
        segs.append({"type": "outro",  "start": outro_start,"end": round(duration, 2), "bars": bar_count(outro_start, duration)})

    return segs or [{"type": "unknown", "start": 0.0, "end": round(duration, 2), "bars": bar_count(0, duration)}]


def _energy_curve(audio: np.ndarray) -> list:
    """RMS energy per 100 ms frame, normalised 0-1."""
    hop = int(SAMPLE_RATE * 0.1)
    energies = [
        float(np.mean(audio[i: i + hop].astype(np.float64) ** 2))
        for i in range(0, len(audio) - hop, hop)
    ]
    if not energies:
        return []
    mx = max(energies) or 1.0
    return [round(e / mx, 4) for e in energies]


def _lufs(audio: np.ndarray) -> float:
    """Integrated loudness via EBU R 128 (duplicates mono to stereo)."""
    try:
        stereo = np.stack([audio, audio], axis=1)
        _, _, integrated, _ = es.LoudnessEBUR128(sampleRate=SAMPLE_RATE)(stereo)
        return round(float(integrated), 1)
    except Exception:
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        return round(20.0 * np.log10(max(rms, 1e-10)), 1)


def _dynamic_range(audio: np.ndarray) -> float:
    """Peak-to-RMS ratio in dB."""
    peak = float(np.max(np.abs(audio)))
    rms  = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < 1e-10 or peak < 1e-10:
        return 0.0
    return round(20.0 * np.log10(peak / rms), 1)


def _spectral(audio: np.ndarray) -> dict:
    """Mean spectral centroid (Hz), brightness, and bass intensity."""
    frame_size = 2048
    hop_size   = 1024
    win_algo   = es.Windowing(type="hann")
    spec_algo  = es.Spectrum(size=frame_size)

    n_bins      = frame_size // 2 + 1
    freqs_axis  = np.linspace(0, SAMPLE_RATE / 2, n_bins)
    low_end_bin = round(250  * n_bins / (SAMPLE_RATE / 2))   # ~6
    high_start  = round(1500 * n_bins / (SAMPLE_RATE / 2))   # ~70

    centroids, brightnesses, bass_vals = [], [], []

    for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size):
        spectrum = spec_algo(win_algo(frame))
        total = float(np.sum(spectrum)) + 1e-10

        centroids.append(float(np.dot(freqs_axis, spectrum)) / total)
        brightnesses.append(float(np.sum(spectrum[high_start:])) / total)
        bass_vals.append(float(np.sum(spectrum[1: low_end_bin + 1])) / total)

    if not centroids:
        return {"centroid": 0.0, "brightness": 0.0, "bass_intensity": 0.0}

    return {
        "centroid":      round(float(np.mean(centroids)), 1),
        "brightness":    round(float(np.mean(brightnesses)), 4),
        "bass_intensity": round(float(np.mean(bass_vals)), 4),
    }


def _stereo_width(file_path: str) -> float:
    """
    L/R decorrelation: 0 = mono, 1 = maximum stereo width.
    Uses AudioLoader; returns 0 for mono files.
    """
    try:
        audio_data, sr, n_ch, *_ = es.AudioLoader(filename=file_path)()
        if n_ch < 2:
            return 0.0
        # AudioLoader returns interleaved stereo as flat array → reshape
        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(-1, n_ch)
        left, right = audio_data[:, 0], audio_data[:, 1]
        if len(left) < 2:
            return 0.0
        corr = float(np.corrcoef(left, right)[0, 1])
        return round(float(np.clip((1.0 - corr) / 2.0, 0.0, 1.0)), 3)
    except Exception as exc:
        logger.debug("Stereo width failed (probably mono): %s", exc)
        return 0.0


def _waveform_rgb(audio: np.ndarray) -> dict:
    """
    Per-10ms frame amplitude in 3 bands for Pixi.js RGB waveform.
    Returns {"low": [...], "mid": [...], "high": [...]} normalised 0-1.
    """
    frame_size = 1024
    hop_size   = int(SAMPLE_RATE * 0.01)   # 10 ms ≈ 441 samples
    n_bins     = frame_size // 2 + 1

    low_end = round(250  * n_bins / (SAMPLE_RATE / 2))   # ~6
    mid_end = round(4000 * n_bins / (SAMPLE_RATE / 2))   # ~93

    win_algo  = es.Windowing(type="hann", size=frame_size)
    spec_algo = es.Spectrum(size=frame_size)

    low_vals, mid_vals, high_vals = [], [], []

    for frame in es.FrameGenerator(audio, frameSize=frame_size, hopSize=hop_size,
                                    startFromZero=True):
        spectrum = spec_algo(win_algo(frame))
        low_vals.append(float(np.sqrt(np.mean(spectrum[1:  low_end + 1] ** 2) + 1e-20)))
        mid_vals.append(float(np.sqrt(np.mean(spectrum[low_end: mid_end]  ** 2) + 1e-20)))
        high_vals.append(float(np.sqrt(np.mean(spectrum[mid_end:]          ** 2) + 1e-20)))

    def _norm(vals: list) -> list:
        mx = max(vals) if vals else 1.0
        if mx < 1e-10:
            return [0.0] * len(vals)
        return [round(v / mx, 4) for v in vals]

    return {"low": _norm(low_vals), "mid": _norm(mid_vals), "high": _norm(high_vals)}


def _update(job_id: Optional[str], **kwargs) -> None:
    if job_id is None:
        return
    try:
        from app.jobs import update_job
        update_job(job_id, **kwargs)
    except Exception as exc:
        logger.warning("[%s] Could not update job: %s", job_id, exc)
