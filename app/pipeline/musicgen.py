"""
MusicGen intro/outro generation — Step 7 of the audio pipeline.

Model: facebook/musicgen-melody (via HuggingFace transformers, NOT audiocraft).
  - 32 kHz output audio
  - Text + melody-audio conditioning (optional)
  - Conditioning: first 10 s of drums+bass+melody mix (no vocals)
  - Generates 3 intro + 3 outro variants, phrase-quantized to BPM

audiocraft is incompatible with Python 3.12 (spaCy/thinc).
Same facebook/musicgen-melody checkpoint via transformers.MusicgenMelody*.

Memory: model is ~2 GB on CPU. Loaded once, freed after all 6 generations.
"""

import gc
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T

logger = logging.getLogger("dj-generator.musicgen")

_MODEL_ID = "facebook/musicgen-melody"
_OUTPUT_SR = 32_000          # musicgen-melody native output sample rate
_COND_SR = 32_000            # conditioning audio must be at this rate
_COND_SECONDS = 10           # seconds of stem mix used for conditioning
_FRAME_RATE = 50             # tokens per second (musicgen-melody default)
_DEFAULT_BARS = 8            # bars per generated variant
_MIN_SECONDS = 12.0          # floor to ensure >10 000 ms output (BUILD_PLAN assertion)

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _genre(bpm: float) -> str:
    if bpm < 100:
        return "deep house"
    elif bpm < 120:
        return "house"
    elif bpm < 135:
        return "tech house"
    elif bpm < 152:
        return "techno"
    elif bpm < 175:
        return "drum and bass"
    return "hardcore"


_INTRO_PROMPTS = [
    "{bpm:.0f} BPM, {key}, {genre}, progressive build-up, drums intro, no vocals, club music",
    "{bpm:.0f} BPM, {key}, {genre}, energetic intro, bass and drums, driving rhythm, no singing",
    "{bpm:.0f} BPM, {key}, {genre}, hypnotic intro, building energy, minimal, instrumental",
]
_OUTRO_PROMPTS = [
    "{bpm:.0f} BPM, {key}, {genre}, fade out ending, reverb tail, no vocals, club music",
    "{bpm:.0f} BPM, {key}, {genre}, outro breakdown, minimal, fading drums",
    "{bpm:.0f} BPM, {key}, {genre}, atmospheric outro, ambient decay, instrumental",
]


def _build_prompt(analysis: dict, beats_data: dict, variant_idx: int, is_outro: bool) -> str:
    bpm = float(beats_data.get("bpm_precise", analysis.get("bpm", 128.0)))
    key = analysis.get("key", "Am")
    g = _genre(bpm)
    templates = _OUTRO_PROMPTS if is_outro else _INTRO_PROMPTS
    return templates[variant_idx % len(templates)].format(bpm=bpm, key=key, genre=g)


# ---------------------------------------------------------------------------
# Conditioning audio
# ---------------------------------------------------------------------------

def _load_conditioning(stems: dict) -> Optional[np.ndarray]:
    """
    Mix drums + bass + melody stems (no vocals), trim to _COND_SECONDS,
    resample to _COND_SR. Returns (samples,) float32 numpy array or None.
    """
    to_mix = []
    for stem_name in ("drums", "bass", "melody"):
        path = stems.get(stem_name)
        if not path or not Path(path).exists():
            logger.warning("Stem '%s' not found — excluded from conditioning mix", stem_name)
            continue
        try:
            wave, sr = torchaudio.load(path)
            if wave.shape[0] > 1:
                wave = wave.mean(dim=0, keepdim=True)
            if sr != _COND_SR:
                wave = T.Resample(orig_freq=sr, new_freq=_COND_SR)(wave)
            wave = wave[:, : _COND_SECONDS * _COND_SR]
            to_mix.append(wave)
        except Exception as exc:
            logger.warning("Could not load stem '%s': %s", stem_name, exc)

    if not to_mix:
        return None

    max_len = max(w.shape[1] for w in to_mix)
    mixed = torch.zeros(1, max_len)
    for w in to_mix:
        mixed[:, : w.shape[1]] += w

    peak = mixed.abs().max().item()
    if peak > 1e-8:
        mixed = mixed / peak

    return mixed[0].numpy().astype(np.float32)


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------

def _max_new_tokens(bpm: float, bars: int) -> int:
    """Phrase-quantized token count — at least _MIN_SECONDS of audio."""
    seconds_per_bar = 4.0 * 60.0 / bpm
    target = max(_MIN_SECONDS, bars * seconds_per_bar)
    return int(target * _FRAME_RATE)


def _fade(audio: np.ndarray, sr: int, is_outro: bool) -> np.ndarray:
    """
    Intro: 0.5 s fade-in at start.
    Outro: 3 s fade-out at end (reverb tail effect).
    """
    audio = audio.copy().astype(np.float32)
    if is_outro:
        n = min(int(3.0 * sr), len(audio))
        audio[-n:] *= np.linspace(1.0, 0.0, n)
    else:
        n = min(int(0.5 * sr), len(audio))
        audio[:n] *= np.linspace(0.0, 1.0, n)
    return audio


def _generate_one(
    model,
    processor,
    prompt: str,
    conditioning: Optional[np.ndarray],
    max_new_tokens: int,
    seed: int,
) -> np.ndarray:
    """Single MusicGen forward pass. Returns (samples,) float32 at _OUTPUT_SR."""
    torch.manual_seed(seed)

    if conditioning is not None:
        inputs = processor(
            audio=[conditioning],
            sampling_rate=_COND_SR,
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )
    else:
        inputs = processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        )

    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=max_new_tokens)

    # output: (batch=1, channels=1, samples)
    return output[0, 0].cpu().numpy().astype(np.float32)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_variations(
    stems: dict,
    analysis: dict,
    beats_data: dict,
    output_dir: str,
    job_id: Optional[str] = None,
    bars: int = _DEFAULT_BARS,
) -> dict:
    """
    MusicGen Step 7: generate 3 intro + 3 outro WAV variants.

    Args:
        stems:       {"drums": path, "bass": path, "melody": path, "vocals": path}
        analysis:    Harmony/analysis dict (key, bpm from essentia or omarrq).
        beats_data:  allin1fix beats dict (bpm_precise, etc.).
        output_dir:  Directory to write intro_0.wav … outro_2.wav.
        job_id:      Celery job ID for Redis progress updates.
        bars:        Bars to generate per variant (phrase-quantized to BPM).

    Returns:
        {
          "intros": [path | None, path | None, path | None],
          "outros": [path | None, path | None, path | None],
        }
        None entries indicate a failed generation (logged as error).
    """
    _update(job_id, progress=72, current_step="musicgen")
    t0 = time.time()

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bpm = float(beats_data.get("bpm_precise", analysis.get("bpm", 128.0)))
    max_tokens = _max_new_tokens(bpm, bars)
    logger.info(
        "[%s] MusicGen starting — model=%s  BPM=%.1f  bars=%d  max_tokens=%d",
        job_id, _MODEL_ID, bpm, bars, max_tokens,
    )

    conditioning = _load_conditioning(stems)
    if conditioning is not None:
        logger.info("[%s] Conditioning audio: %.1fs at %d Hz", job_id, len(conditioning) / _COND_SR, _COND_SR)
    else:
        logger.warning("[%s] No conditioning audio — text-only generation", job_id)

    # Load model once for all 6 generations.
    # Use MusicgenMelodyProcessor directly — AutoProcessor looks for
    # processor_config.json which musicgen-melody doesn't have (it has
    # preprocessor_config.json), causing a 404 → PermissionError cascade.
    logger.info("[%s] Loading %s …", job_id, _MODEL_ID)
    from transformers import MusicgenMelodyProcessor, MusicgenMelodyForConditionalGeneration
    processor = MusicgenMelodyProcessor.from_pretrained(_MODEL_ID)
    model = MusicgenMelodyForConditionalGeneration.from_pretrained(_MODEL_ID)
    model.eval()
    logger.info("[%s] Model loaded", job_id)

    intros: list = []
    outros: list = []
    done = 0
    total = 6

    for cfg in [
        {"prefix": "intro", "is_outro": False, "bucket": intros},
        {"prefix": "outro", "is_outro": True,  "bucket": outros},
    ]:
        for i in range(3):
            prompt = _build_prompt(analysis, beats_data, i, cfg["is_outro"])
            seed = 42 + i + (100 if cfg["is_outro"] else 0)
            out_path = str(out_dir / f"{cfg['prefix']}_{i}.wav")

            logger.info("[%s] Generating %s_%d (seed=%d) — %r", job_id, cfg["prefix"], i, seed, prompt)
            t_gen = time.time()
            try:
                audio = _generate_one(model, processor, prompt, conditioning, max_tokens, seed)
                audio = _fade(audio, sr=_OUTPUT_SR, is_outro=cfg["is_outro"])

                torchaudio.save(
                    out_path,
                    torch.from_numpy(audio).unsqueeze(0),
                    _OUTPUT_SR,
                )
                cfg["bucket"].append(out_path)
                logger.info(
                    "[%s] %s_%d done in %.1fs — %.2f s audio → %s",
                    job_id, cfg["prefix"], i, time.time() - t_gen,
                    len(audio) / _OUTPUT_SR, out_path,
                )
            except Exception as exc:
                logger.error("[%s] %s_%d failed: %s", job_id, cfg["prefix"], i, exc)
                cfg["bucket"].append(None)

            done += 1
            _update(job_id, progress=72 + int(done / total * 23), current_step=f"musicgen_{cfg['prefix']}_{i}")

    # Free ~2 GB before next pipeline step
    del model, processor
    gc.collect()
    torch.cuda.empty_cache()

    elapsed = time.time() - t0
    good_intros = sum(1 for p in intros if p)
    good_outros = sum(1 for p in outros if p)
    logger.info(
        "[%s] MusicGen done in %.1fs — intros=%d/3  outros=%d/3",
        job_id, elapsed, good_intros, good_outros,
    )
    _update(job_id, progress=95, current_step="musicgen_done")

    return {"intros": intros, "outros": outros}


def _update(job_id: Optional[str], **kwargs) -> None:
    if job_id is None:
        return
    try:
        from app.jobs import update_job
        update_job(job_id, **kwargs)
    except Exception as exc:
        logger.warning("[%s] Job update failed: %s", job_id, exc)
