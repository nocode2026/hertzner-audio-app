import bisect
import logging
from typing import Optional

logger = logging.getLogger("dj-generator.cue-points")

# UI colors
_COLORS = {
    "mix_in":    "#00E676",
    "mix_out":   "#F44336",
    "drop":      "#FF6D00",
    "breakdown": "#2196F3",
    "vocal_in":  "#9C27B0",
    "8bar":      "#FFEB3B",
}


def generate_cue_points(
    analysis: dict,
    beats_data: dict,
    vocal_stem_path: Optional[str] = None,
) -> list:
    """
    Generate beat-snapped cue points from Essentia + allin1fix analysis.

    Parameters
    ----------
    analysis:        Essentia result dict (segments, duration, energy_curve, …)
    beats_data:      allin1fix result dict (beats, downbeats, segments, phrases, …)
    vocal_stem_path: Optional path to vocals.wav for vocal-start detection

    Returns
    -------
    list of cue-point dicts sorted by time:
        {"id": str, "label": str, "time": float, "beat_number": int, "color": str}
    """
    beats     = beats_data.get("beats", [])
    downbeats = beats_data.get("downbeats", [])
    allin1_segs  = beats_data.get("segments", [])
    phrases_8bar = beats_data.get("phrases", {}).get("8bar", [])

    essentia_segs = analysis.get("segments", [])
    duration      = float(analysis.get("duration", 0.0))

    snap_ref = downbeats if downbeats else beats  # prefer downbeat grid

    cues = []

    # --- mix_in: first downbeat at/after end of intro ---
    intro_end = _seg_end(allin1_segs, essentia_segs, ["intro"], default=duration * 0.12)
    mix_in_t  = _snap(intro_end, snap_ref, beats, prefer="after")
    cues.append(_cue("mix_in", "Mix In", mix_in_t, beats))

    # --- mix_out: last downbeat at/before outro start ---
    outro_start = _seg_start(allin1_segs, essentia_segs, ["outro"], default=duration * 0.88)
    mix_out_t   = _snap(outro_start, snap_ref, beats, prefer="before")
    cues.append(_cue("mix_out", "Mix Out", mix_out_t, beats))

    # --- drop: first chorus/inst/drop segment ---
    drop_t = _seg_start(allin1_segs, essentia_segs, ["chorus", "inst", "drop"], default=None)
    if drop_t is not None:
        cues.append(_cue("drop", "Drop", _snap(drop_t, snap_ref, beats), beats))

    # --- breakdown: first break/bridge/breakdown segment ---
    bd_t = _seg_start(allin1_segs, essentia_segs, ["break", "bridge", "breakdown"], default=None)
    if bd_t is not None:
        cues.append(_cue("breakdown", "Breakdown", _snap(bd_t, snap_ref, beats), beats))

    # --- vocal_in: first frame with significant vocal energy ---
    if vocal_stem_path:
        voc_t = _detect_vocal_start(vocal_stem_path)
        if voc_t is not None:
            cues.append(_cue("vocal_in", "Vocal In", _snap(voc_t, beats, beats), beats))

    # --- 8-bar phrase markers ---
    for i, t in enumerate(phrases_8bar):
        cues.append(_cue(f"8bar_{i}", f"8 Bar {i + 1}", _snap(t, beats, beats), beats, key="8bar"))

    cues.sort(key=lambda c: c["time"])
    logger.info("Generated %d cue points", len(cues))
    return cues


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _snap(time: float, reference: list, beats: list, prefer: str = "nearest") -> float:
    """
    Snap `time` to the nearest entry in `reference`.
    Falls back to `beats` if `reference` is empty.
    `prefer` can be "nearest", "after", or "before".
    Returns the exact float from the list (so beat-snap assertions pass).
    """
    pool = reference if reference else beats
    if not pool:
        return time

    idx = bisect.bisect_left(pool, time)

    if prefer == "after":
        if idx < len(pool):
            return pool[idx]
        return pool[-1]
    if prefer == "before":
        if idx > 0:
            return pool[idx - 1]
        return pool[0]

    # nearest
    if idx == 0:
        return pool[0]
    if idx >= len(pool):
        return pool[-1]
    before = pool[idx - 1]
    after  = pool[idx]
    return before if (time - before) <= (after - time) else after


def _beat_number(time: float, beats: list) -> int:
    """1-indexed position of the closest beat to `time`."""
    if not beats:
        return 1
    idx = bisect.bisect_left(beats, time)
    if idx == 0:
        return 1
    if idx >= len(beats):
        return len(beats)
    before = beats[idx - 1]
    after  = beats[idx]
    closest_idx = idx - 1 if (time - before) <= (after - time) else idx
    return closest_idx + 1  # 1-indexed


def _cue(id: str, label: str, time: float, beats: list, key: Optional[str] = None) -> dict:
    return {
        "id":    id,
        "label": label,
        "time":  round(time, 3),
        "beat":  _beat_number(time, beats),
        "color": _COLORS.get(key or id, "#FFFFFF"),
    }


def _seg_end(a1_segs: list, ess_segs: list, labels: list, default: float) -> float:
    """Return end time of the first matching segment, preferring allin1fix labels."""
    for seg in a1_segs:
        if seg.get("label") in labels:
            return float(seg["end"])
    for seg in ess_segs:
        if seg.get("label") in labels or seg.get("type") in labels:
            return float(seg["end"])
    return default


def _seg_start(a1_segs: list, ess_segs: list, labels: list, default) -> Optional[float]:
    """Return start time of the first matching segment."""
    for seg in a1_segs:
        if seg.get("label") in labels:
            return float(seg["start"])
    for seg in ess_segs:
        if seg.get("label") in labels or seg.get("type") in labels:
            return float(seg["start"])
    return default


def _detect_vocal_start(vocal_stem_path: str) -> Optional[float]:
    """
    Find the first time the vocal stem has significant energy (>5 % of peak).
    Uses 50 ms frames; returns None if the stem is silent throughout.
    """
    try:
        import numpy as np
        import essentia.standard as es

        SR      = 44100
        hop     = int(SR * 0.05)   # 50 ms
        audio   = es.MonoLoader(filename=str(vocal_stem_path), sampleRate=SR)()
        if len(audio) < hop:
            return None

        energies = [
            float(np.mean(audio[i: i + hop].astype(np.float64) ** 2))
            for i in range(0, len(audio) - hop, hop)
        ]
        threshold = max(energies) * 0.05
        for i, e in enumerate(energies):
            if e > threshold:
                return round(i * hop / SR, 3)
        return None
    except Exception as exc:
        logger.debug("Vocal start detection failed: %s", exc)
        return None
