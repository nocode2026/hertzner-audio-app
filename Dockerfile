FROM python:3.12-slim

# System dependencies - MUSZĄ być przed pip install
RUN apt-get update && apt-get install -y \
    gcc g++ make cmake git ffmpeg \
    libsndfile1 libsndfile1-dev \
    libavcodec-dev libavformat-dev libavutil-dev \
    libsox-dev sox \
    rubberband-cli \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# KROK 1: PyTorch CPU (musi być PIERWSZY - natten i inne go potrzebują)
RUN pip install --no-cache-dir \
    torch==2.7.0 torchaudio==2.7.0 \
    --index-url https://download.pytorch.org/whl/cpu

# KROK 2: natten CPU-only (MUSI być po torch, przed allin1fix)
# Dla CPU: pip install natten działa bez CUDA
RUN pip install --no-cache-dir natten==0.21.6

# KROK 3a: madmom (wymagany przez allin1fix, instalacja z GitHub)
RUN pip install --no-cache-dir 'git+https://github.com/CPJKU/madmom'

# KROK 3b: allin1fix (używa natten>=0.17.5 - 0.21.6 to spełnia)
RUN pip install --no-cache-dir all-in-one-fix --no-build-isolation

# KROK 3c: natten CPU fix — get_device_cc() crashes on CPU-only torch (no CUDA)
RUN python3 -c "import pathlib; p = pathlib.Path('/usr/local/lib/python3.12/site-packages/natten/utils/misc.py'); src = p.read_text(); old = '    major, minor = torch.cuda.get_device_capability(device_index)\n    return major * 10 + minor'; new = '    if not torch.cuda.is_available():\n        return 0\n    major, minor = torch.cuda.get_device_capability(device_index)\n    return major * 10 + minor'; p.write_text(src.replace(old, new)); print('natten patched' if old in src else 'patch already applied or pattern not found')" \
    && python3 -c "import allin1fix; print('allin1fix import OK')"

# KROK 4: Essentia (wymaga --pre bo to wersja dev)
RUN pip install --no-cache-dir --pre essentia

# KROK 5: Demucs (nasz główny, osobny od demucs-infer w allin1fix)
RUN pip install --no-cache-dir demucs

# KROK 6: MusicGen przez HuggingFace Transformers
# audiocraft niekompatybilny z Python 3.12 (spaCy/thinc bez wheela)
# transformers daje ten sam model musicgen-melody bez problematycznych zależności
RUN pip install --no-cache-dir transformers accelerate encodec

# KROK 7: Reszta stacku
RUN pip install --no-cache-dir \
    pyrubberband \
    pydub \
    fastapi==0.111.0 \
    uvicorn==0.29.0 \
    celery==5.3.6 \
    redis==5.0.4 \
    python-multipart==0.0.9 \
    pydantic==2.7.0 \
    filetype \
    numpy scipy

# KROK 8: OMAR-RQ
RUN pip install --no-cache-dir git+https://github.com/MTG/OMAR-RQ.git

COPY . .

# Non-root user — Celery warns on root, production best practice
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/.cache \
    && chown -R appuser:appuser /app
USER appuser

# Unified cache dir for HuggingFace, torch, etc.
ENV XDG_CACHE_HOME=/app/.cache \
    HF_HOME=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
