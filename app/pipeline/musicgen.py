"""
MusicGen intro/outro generation — Step 7 of the audio pipeline.

Model: facebook/musicgen-melody (via HuggingFace transformers, NOT audiocraft).
  - 32 kHz output audio
  - Text + melody-audio conditioning (optional)
    - Conditioning: highest-energy 10 s window from drums+bass+melody mix (no vocals)
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
_COND_WINDOW_STRIDE = 1.0    # seconds between candidate windows for conditioning
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
    # Weighted blend reduces artifacts from the "other" stem and keeps groove anchors.
    stem_weights = {
        "drums": 0.50,
        "bass": 0.35,
        "melody": 0.15,
    }

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
            to_mix.append(wave * stem_weights[stem_name])
        except Exception as exc:
            logger.warning("Could not load stem '%s': %s", stem_name, exc)

    if not to_mix:
        return None

    max_len = max(w.shape[1] for w in to_mix)
    mixed = torch.zeros(1, max_len)
    for w in to_mix:
        mixed[:, : w.shape[1]] += w

    # Pick the most energetic conditioning window instead of always taking
    # the first seconds (often sparse intros that lead to noisy generations).
    target_len = int(_COND_SECONDS * _COND_SR)
    if mixed.shape[1] > target_len:
        stride = max(1, int(_COND_WINDOW_STRIDE * _COND_SR))
        best_start = 0
        best_rms = -1.0
        for start in range(0, mixed.shape[1] - target_len + 1, stride):
            chunk = mixed[:, start : start + target_len]
            rms = torch.sqrt(torch.mean(chunk * chunk)).item()
            if rms > best_rms:
                best_rms = rms
                best_start = start
        mixed = mixed[:, best_start : best_start + target_len]
    else:
        mixed = mixed[:, :target_len]

    # Loudness normalize and apply gentle soft-clip to avoid brittle clipping artifacts.
    rms = torch.sqrt(torch.mean(mixed * mixed)).item()
    if rms > 1e-8:
        mixed = mixed * (0.12 / rms)
    mixed = torch.tanh(mixed * 1.3)

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


def _spectral_flatness(audio: np.ndarray) -> float:
    """Return mean spectral flatness (0 tonal .. 1 noise-like)."""
    if audio.size < 2048:
        return 1.0

    x = audio.astype(np.float32)
    frame = 2048
    hop = 512
    flats = []
    eps = 1e-10

    for i in range(0, len(x) - frame + 1, hop):
        w = x[i : i + frame] * np.hanning(frame)
        spec = np.abs(np.fft.rfft(w)) + eps
        gm = float(np.exp(np.mean(np.log(spec))))
        am = float(np.mean(spec))
        flats.append(gm / am)

    return float(np.mean(flats)) if flats else 1.0


def _zero_crossing_rate(audio: np.ndarray) -> float:
    if audio.size < 2:
        return 1.0
    signs = np.signbit(audio)
    return float(np.mean(signs[1:] != signs[:-1]))


def _is_noise_like(audio: np.ndarray) -> bool:
    """
    Heuristic gate for pathological generations that sound like broadband noise.
    """
    if audio.size == 0:
        return True

    rms = float(np.sqrt(np.mean(audio * audio)))
    if rms < 1e-4:
        return True

    flatness = _spectral_flatness(audio)
    zcr = _zero_crossing_rate(audio)
    return flatness > 0.45 and zcr > 0.18


def _load_stem_audio(path: Optional[str], target_sr: int) -> Optional[np.ndarray]:
    if not path or not Path(path).exists():
        return None
    try:
        wave, sr = torchaudio.load(path)
        if wave.shape[0] > 1:
            wave = wave.mean(dim=0, keepdim=True)
        if sr != target_sr:
            wave = T.Resample(orig_freq=sr, new_freq=target_sr)(wave)
        return wave[0].numpy().astype(np.float32)
    except Exception as exc:
        logger.warning("Could not load fallback stem '%s': %s", path, exc)
        return None


def _extract_window(wave: np.ndarray, start: int, length: int) -> np.ndarray:
    if length <= 0:
        return np.zeros(0, dtype=np.float32)
    if wave.size == 0:
        return np.zeros(length, dtype=np.float32)
    if wave.size >= start + length:
        return wave[start : start + length].astype(np.float32)

    # If source is shorter than target, tile and trim.
    reps = int(np.ceil((start + length) / max(1, wave.size)))
    tiled = np.tile(wave, reps)
    return tiled[start : start + length].astype(np.float32)


def _stem_fallback(
    stems: dict,
    seconds: float,
    is_outro: bool,
    variant_idx: int,
    sr: int = _OUTPUT_SR,
) -> Optional[np.ndarray]:
    """
    Build a musically coherent fallback directly from source stems.
    This guarantees style/tonality continuity with the original track.
    """
    drums = _load_stem_audio(stems.get("drums"), sr)
    bass = _load_stem_audio(stems.get("bass"), sr)
    melody = _load_stem_audio(stems.get("melody"), sr)

    available = [w for w in (drums, bass, melody) if w is not None and w.size > 0]
    if not available:
        return None

    out_len = max(1, int(seconds * sr))
    min_len = min(w.size for w in available)
    # Variant-dependent offset picks different musical moments while avoiding tiny tails.
    max_start = max(0, min_len - out_len - sr)
    ratio = (variant_idx + 1) / 4.0
    start = int(max_start * ratio)

    d = _extract_window(drums, start, out_len) if drums is not None else np.zeros(out_len, dtype=np.float32)
    b = _extract_window(bass, start, out_len) if bass is not None else np.zeros(out_len, dtype=np.float32)
    m = _extract_window(melody, start, out_len) if melody is not None else np.zeros(out_len, dtype=np.float32)

    t = np.linspace(0.0, 1.0, out_len, dtype=np.float32)
    if is_outro:
        env_d = np.clip(1.0 - t * 0.9, 0.0, 1.0)
        env_b = np.clip(1.0 - t * 1.1, 0.0, 1.0)
        env_m = np.clip(1.0 - t * 1.3, 0.0, 1.0)
    else:
        env_d = np.clip(t * 1.2, 0.0, 1.0)
        env_b = np.clip((t - 0.1) * 1.4, 0.0, 1.0)
        env_m = np.clip((t - 0.25) * 1.8, 0.0, 1.0)

    mix = (0.95 * d * env_d) + (0.8 * b * env_b) + (0.6 * m * env_m)

    peak = float(np.max(np.abs(mix)))
    if peak > 1e-8:
        mix = mix * (0.92 / peak)

    return mix.astype(np.float32)


def _estimate_source_seconds(stems: dict) -> float:
    """Estimate source duration from first available stem file."""
    for stem_name in ("drums", "bass", "melody", "vocals"):
        path = stems.get(stem_name)
        if not path or not Path(path).exists():
            continue
        try:
            info = torchaudio.info(path)
            if info.sample_rate > 0 and info.num_frames > 0:
                return float(info.num_frames) / float(info.sample_rate)
        except Exception:
            continue
    return 0.0


def _generate_one(
    model,
    processor,
    prompt: str,
    conditioning: Optional[np.ndarray],
    max_new_tokens: int,
    seed: int,
    guidance_scale: float,
    temperature: float,
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
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            guidance_scale=guidance_scale,
            temperature=temperature,
            top_k=100,
            top_p=0.95,
        )

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

    source_seconds = _estimate_source_seconds(stems)
    beat_count = len(beats_data.get("beats", []) or [])
    use_stem_only = beat_count == 0 or source_seconds < 8.0

    if use_stem_only:
        logger.warning(
            "[%s] MusicGen AI skipped (beat_count=%d, source=%.1fs); using stem fallback mode",
            job_id,
            beat_count,
            source_seconds,
        )

    model = None
    processor = None
    if not use_stem_only:
        # Load model once for all 6 generations.
        # Use MusicgenMelodyProcessor directly — AutoProcessor looks for
        # processor_config.json which musicgen-melody doesn't have (it has
        # preprocessor_config.json), causing a 404 → PermissionError cascade.
        logger.info("[%s] Loading %s …", job_id, _MODEL_ID)
        from transformers import MusicgenMelodyProcessor, MusicgenMelodyForConditionalGeneration

        try:
            processor = MusicgenMelodyProcessor.from_pretrained(_MODEL_ID)
            model = MusicgenMelodyForConditionalGeneration.from_pretrained(_MODEL_ID)
            model.eval()
            logger.info("[%s] Model loaded", job_id)
        except Exception as exc:
            logger.error("[%s] MusicGen model load failed: %s; switching to stem fallback mode", job_id, exc)
            use_stem_only = True

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
                target_seconds = max_tokens / _FRAME_RATE
                if use_stem_only:
                    fallback = _stem_fallback(
                        stems=stems,
                        seconds=target_seconds,
                        is_outro=cfg["is_outro"],
                        variant_idx=i,
                    )
                    if fallback is None:
                        raise RuntimeError("stem fallback unavailable (missing stems)")
                    audio = fallback
                else:
                    audio = _generate_one(
                        model,
                        processor,
                        prompt,
                        conditioning,
                        max_tokens,
                        seed,
                        guidance_scale=3.5,
                        temperature=0.95,
                    )
                    if _is_noise_like(audio):
                        logger.warning(
                            "[%s] %s_%d flagged as noise-like; retrying with tighter sampling",
                            job_id,
                            cfg["prefix"],
                            i,
                        )
                        audio = _generate_one(
                            model,
                            processor,
                            prompt,
                            conditioning,
                            max_tokens,
                            seed + 777,
                            guidance_scale=5.0,
                            temperature=0.7,
                        )

                    if _is_noise_like(audio):
                        logger.warning(
                            "[%s] %s_%d still noise-like after retry; switching to stem fallback",
                            job_id,
                            cfg["prefix"],
                            i,
                        )
                        fallback = _stem_fallback(
                            stems=stems,
                            seconds=target_seconds,
                            is_outro=cfg["is_outro"],
                            variant_idx=i,
                        )
                        if fallback is not None:
                            audio = fallback
                        else:
                            logger.warning(
                                "[%s] %s_%d fallback unavailable (missing stems); keeping AI output",
                                job_id,
                                cfg["prefix"],
                                i,
                            )

                audio = _fade(audio, sr=_OUTPUT_SR, is_outro=cfg["is_outro"])

                torchaudio.save(
                    out_path,
                    torch.from_numpy(audio).unsqueeze(0),
                    _OUTPUT_SR,
                    encoding="PCM_S",
                    bits_per_sample=16,
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
    if model is not None and processor is not None:
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
