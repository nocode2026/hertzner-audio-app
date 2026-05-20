# KNOWN_ISSUES — Znane błędy i rozwiązania
# DJ Intro/Outro Generator

> Błędy odkryte PRZED budowaniem — na podstawie researchu.
> Błędy odkryte PODCZAS budowania dopisywane na górze.

---

## [FAZA 2.6] — AutoProcessor.from_pretrained() failing dla musicgen-melody

**Symptom:**
```
404 Not Found: facebook/musicgen-melody/resolve/main/processor_config.json
PermissionError at /app/.cache/huggingface
```

**Przyczyna:** `AutoProcessor` szuka `processor_config.json` → 404 (plik nie istnieje w repo).
Następnie próbuje zakeszować 404 → PermissionError na `/app/.cache`. Podwójny błąd.
Repo ma `preprocessor_config.json` (nie `processor_config.json`).

**Rozwiązanie:**
```python
# Zamiast:
from transformers import AutoProcessor
processor = AutoProcessor.from_pretrained("facebook/musicgen-melody")

# Używaj:
from transformers import MusicgenMelodyProcessor
processor = MusicgenMelodyProcessor.from_pretrained("facebook/musicgen-melody")
```

**Zapobieganie:** Zawsze używaj konkretnej klasy procesora dla musicgen-melody.
Zastosowane w `app/pipeline/musicgen.py`.

---

## [FAZA 2.6] — MusicGen model OOM na dev machine

**Symptom:** `exit code 137` (OOM killed) przy ładowaniu `facebook/musicgen-melody`

**Przyczyna:** Model waży ~2GB na dysku, ładuje ~4-6GB RAM. Dev machine ma za mało RAM
gdy łączy się z OS, innymi procesami i tmpfs.

**Rozwiązanie:** Pełna weryfikacja generacji na Hetzner CPX41 (16GB RAM).
Kod jest poprawny — processor pipeline zweryfikowany lokalnie (input_ids: [1, 9]).
Pamiętaj: uruchamiaj Demucs → zwolnij RAM → uruchamiaj MusicGen (nie jednocześnie).

**Zapobieganie:** `del model; gc.collect(); torch.cuda.empty_cache()` po każdym etapie
(już w `app/pipeline/musicgen.py` i `app/pipeline/demucs.py`).

---

## [FAZA 2.5] — OMAR-RQ nie ma wbudowanych klasyfikatorów chord/key

**Symptom:** OMAR-RQ (model `mtg-upf/omar-rq-multifeature-25hz-fsq`) jest modelem
embeddingów (SSL) — `extract_embeddings()` zwraca surowe tensory, nie nazwy akordów.

**Przyczyna:** To model self-supervised — chord/key detection wymaga oddzielnie
wytrenowanych probe classifierów (nie są publicznie dostępne jako gotowe wagi).

**Rozwiązanie zastosowane w omarrq.py:**
1. Embeddingi OMAR-RQ są FAKTYCZNIE ekstrahowane (layer=6, 25Hz, dim=1024) — model działa.
2. Chromagram + Krumhansl-Schmuckler dla key detection (na tym samym audio 24kHz).
3. Template-based chord matching (cosine similarity na HPCP).
4. To podejście daje key confidence=0.962 na syntetycznym A minor — wiarygodne.

**Fallback:** Gdy OMAR-RQ model nie dostępny (brak internetu, OOM) — chromagram analiza
kontynuuje bez embeddingów. `embeddings_shape` = None w wyniku.

**Dla przyszłości:** Jeśli MTG Barcelona wyda gotowe probe weights dla chord/key,
można je wczytać i zamienić KS key detection na predykcję z proby.

---

---

## [PRE-BUILD] — allin1fix wymaga --no-build-isolation

**Symptom:** `pip install all-in-one-fix` kończy się błędem kompilacji

**Przyczyna:** madmom jest instalowany z GitHub podczas instalacji i potrzebuje dostępu do już zainstalowanego torch

**Rozwiązanie:**
```bash
pip install torch>=2.0.0
pip install all-in-one-fix --no-build-isolation
```

**Zapobieganie:** Zawsze instaluj PyTorch PRZED allin1fix. W Dockerfile: osobna warstwa RUN dla torch.

---

## [PRE-BUILD] — allin1fix podwójny Demucs problem

**Symptom:** allin1fix chce uruchomić własny Demucs (demucs-infer) mimo że mamy już stemy

**Przyczyna:** allin1fix domyślnie robi własną separację stemów

**Rozwiązanie:**
```bash
# Zamiast:
allin1fix track.wav

# Używaj:
allin1fix track.wav --stems-from-dir ./stems/ --stems-id "track_id"
```

**Zapobieganie:** Zawsze przekazuj stemy z naszego Demucs pipeline. Dokumentuj w pipeline/allin1fix.py.

---

## [PRE-BUILD] — Essentia wymaga systemowych bibliotek

**Symptom:** `ImportError: libsndfile.so.1: cannot open shared object file`

**Przyczyna:** Essentia zależy od systemowych bibliotek audio

**Rozwiązanie:**
```dockerfile
RUN apt-get install -y \
    libsndfile1 \
    libavcodec-dev \
    libavformat-dev \
    libavutil-dev \
    ffmpeg
```

**Zapobieganie:** Dodaj do Dockerfile przed `pip install essentia`.

---

## [PRE-BUILD] — RAM issue: Demucs + MusicGen jednocześnie

**Symptom:** OOM (Out of Memory) na 16GB RAM

**Przyczyna:** htdemucs ~4GB + MusicGen ~6GB = ~10GB + system overhead = może przekroczyć 16GB

**Rozwiązanie:**
```python
# Po zakończeniu Demucs:
del model
import gc; gc.collect()
import torch; torch.cuda.empty_cache()
# Poczekaj 5s przed uruchomieniem MusicGen
import time; time.sleep(5)
```

**Zapobieganie:** Zawsze zwalniaj RAM po każdym etapie. Nie ładuj dwóch dużych modeli jednocześnie.

---

## [PRE-BUILD] — MP3 offset w allin1fix

**Symptom:** Beat grid jest przesunięty o ~20-40ms dla plików MP3

**Przyczyna:** Różne dekodery MP3 dają różne offsety

**Rozwiązanie:**
```python
# Step 1 pipeline: zawsze konwertuj do WAV przed analizą
import subprocess
subprocess.run(['ffmpeg', '-i', 'input.mp3', '-ar', '44100', 'output.wav'])
```

**Zapobieganie:** Step 1 pipeline zawsze konwertuje do WAV. Nigdy nie analizuj MP3 bezpośrednio.

---

## [PRE-BUILD] — OMAR-RQ model download przy pierwszym uruchomieniu

**Symptom:** Pierwsze uruchomienie trwa bardzo długo (>10 min) bez postępu

**Przyczyna:** Model waży ~1.5GB i jest pobierany przy pierwszym użyciu

**Rozwiązanie:**
```python
# Pre-download modelu przy starcie serwera (nie w trakcie requestu):
# W startup event FastAPI:
@app.on_event("startup")
async def download_models():
    # Inicjalizuj OMAR-RQ żeby pobrał model
    pass
```

**Zapobieganie:** Pre-download wszystkich modeli przy budowaniu Docker image lub przy starcie.

---

<!-- BŁĘDY Z SESJI BUDOWANIA PONIŻEJ -->

## [FAZA 2.2] — Permission error na mounted volumes

**Symptom:** `PermissionError: Permission denied` przy zapisie stemów

**Przyczyna:** Kontener działa jako `appuser` (uid 1000), katalogi tworzone jako root

**Rozwiązanie:**
```bash
sudo chown -R 1000:1000 ~/apps/audio-app/uploads \
  ~/apps/audio-app/outputs \
  ~/apps/audio-app/models_cache
```

**Zapobieganie:** Dodać do instrukcji deployment

---

## [FAZA 2.2] — audiocraft niekompatybilny z Python 3.12 (spaCy/thinc)

**Symptom:**
`pip install audiocraft` kończy się błędem `Failed building wheel for thinc`

**Przyczyna:**
audiocraft 1.3.0 wymaga `av==11.0.0` (pinned). pip cofa się do audiocraft 1.1.0
który wymaga `spacy==3.5.2` → `thinc<8.2.0` — brak pre-built wheel dla Python 3.12.

**Rozwiązanie:**
Zamiast audiocraft używamy HuggingFace `transformers` — ten sam model
`facebook/musicgen-melody` dostępny przez `MusicgenMelodyForConditionalGeneration`.
```dockerfile
# Zamiast:
RUN pip install --no-cache-dir audiocraft
# Używamy:
RUN pip install --no-cache-dir transformers accelerate encodec
```

**API w musicgen.py:**
```python
from transformers import AutoProcessor, MusicgenMelodyForConditionalGeneration
# zamiast: from audiocraft.models import MusicGen
```

**Zapobieganie:** Nie wracaj do audiocraft na Python 3.12. transformers ma stabilny support i brak spaCy dependency.

---

## [FAZA 0] — natten wymaga instalacji po torch, wersja 0.21.6 dla CPU

**Symptom:** `pip install natten==0.17.5` kończy się błędem "No module named torch"

**Przyczyna:** natten kompiluje się ze źródeł i wymaga torch zainstalowanego WCZEŚNIEJ.
allin1fix wymaga natten>=0.17.5 — wersja 0.21.6 spełnia warunek i działa na CPU.

**Rozwiązanie:**
```dockerfile
RUN pip install torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install natten==0.21.6  # CPU-only, bez CUDA
RUN pip install all-in-one-fix --no-build-isolation
```

**Zapobieganie:** Kolejność w Dockerfile jest krytyczna. Nigdy nie zmieniaj.

---

## [FAZA 0] — pyrubberband wymaga rubberband-cli w systemie

**Symptom:** `pyrubberband` importuje się ale pitch shift nie działa (subprocess error)

**Przyczyna:** pyrubberband to wrapper — wywołuje binarny `rubberband` przez subprocess.

**Rozwiązanie:**
```dockerfile
RUN apt-get install -y rubberband-cli
```

**Zapobieganie:** Zawarte w Dockerfile. Nie usuwaj tej linii.

---

## [FAZA 2.4] — natten 0.17.5 crash na CPU-only PyTorch

**Symptom:** `AssertionError: Torch not compiled with CUDA enabled` przy `import allin1fix`

**Przyczyna:** `natten/utils/misc.py` → `get_device_cc()` wywołuje `torch.cuda.get_device_capability()` na poziomie modułu bez sprawdzenia `torch.cuda.is_available()`. Crashuje przy CPU-only torch.

**Rozwiązanie:**
```dockerfile
# W Dockerfile, po instalacji allin1fix:
RUN python3 -c "import pathlib; p = pathlib.Path('/usr/local/lib/python3.12/site-packages/natten/utils/misc.py'); src = p.read_text(); old = '    major, minor = torch.cuda.get_device_capability(device_index)\n    return major * 10 + minor'; new = '    if not torch.cuda.is_available():\n        return 0\n    major, minor = torch.cuda.get_device_capability(device_index)\n    return major * 10 + minor'; p.write_text(src.replace(old, new))"
```

**Zapobieganie:** Patch natten w Dockerfile (KROK 3c). Zawarte w aktualnym Dockerfile.

---

## [FAZA 2.4] — allin1fix wymaga stereo audio (2 kanały)

**Symptom:** `expected input to have 2 channels, but got 1 channels instead` przy analizie mono WAV

**Przyczyna:** htdemucs w środku allin1fix oczekuje stereo wejścia.

**Rozwiązanie:** Zawsze konwertuj do stereo przed analizą (Faza 2.6 WAV conversion krok obsłuży to). Lub używaj stems_dir z Demucs — stemy Demucs są zawsze stereo.

**Zapobieganie:** W pipeline zawsze używaj `stems_dir` z Demucs, nie `paths` dla mono plików.

---

## [FAZA 0] — essentia wymaga --pre flag

**Symptom:** `pip install essentia` → "No matching distribution found"

**Przyczyna:** Najnowsza essentia jest wersją dev (2.1b6.dev...) — pip nie pokazuje jej bez --pre.

**Rozwiązanie:**
```bash
pip install --pre essentia
```

**Zapobieganie:** Zawarte w Dockerfile i requirements.txt.
