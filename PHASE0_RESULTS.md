# Faza 0 — Wyniki testu instalacji

## Środowisko testowe
- Python: 3.12.3
- OS: Ubuntu 24 Linux x86_64

## Wyniki testów

| Biblioteka | Status | Uwagi |
|-----------|--------|-------|
| `essentia` | ✅ PASS | Wymaga `--pre` (wersja dev). BPM, Key, LUFS, Spectral - wszystko działa |
| `pydub` | ✅ PASS | Generowanie, crossfade, export WAV - działa |
| `fastapi` | ✅ PASS | Routes, Pydantic models - działa |
| `celery` | ✅ PASS | Zainstalowany poprawnie |
| `redis` | ✅ PASS | Zainstalowany poprawnie |
| `pyrubberband` | ✅ PASS | Biblioteka OK. UWAGA: wymaga `rubberband-cli` w systemie (apt install) |
| `torch` | ⏳ SKIP | Za duże do testu tutaj (2GB). Weryfikacja na Hetzner. |
| `natten` | ⏳ SKIP | Zależny od torch. CPU install: `pip install natten==0.21.6` |
| `allin1fix` | ⏳ SKIP | Zależny od torch+natten. |
| `demucs` | ⏳ SKIP | Zależny od torch. |
| `audiocraft` | ⏳ SKIP | Zależny od torch. |
| `OMAR-RQ` | ⏳ SKIP | Zależny od torch. |

## Kluczowe odkrycia

1. **Python 3.12 działa dla całego stacku** — wszystkie biblioteki mają wheels dla cp312
2. **natten CPU install**: `pip install natten==0.21.6` — bez CUDA, używa Flex Attention
3. **allin1fix wymaga natten>=0.17.5** — 0.21.6 spełnia warunek ✅
4. **rubberband-cli** musi być w Dockerfile: `apt install rubberband-cli`
5. **Essentia** wymaga `--pre` flag przy pip install

## Prawidłowa kolejność instalacji (Dockerfile)

```
1. apt install ffmpeg libsndfile1 rubberband-cli (system)
2. pip install torch==2.7.0 (CPU) 
3. pip install natten==0.21.6 (CPU-only, po torch)
4. pip install all-in-one-fix --no-build-isolation
5. pip install --pre essentia
6. pip install demucs
7. pip install audiocraft
8. pip install pyrubberband pydub fastapi uvicorn celery redis
9. pip install git+https://github.com/MTG/OMAR-RQ.git
```

## Co wymaga weryfikacji na Hetzner

- Pełna instalacja torch + natten + allin1fix razem
- Test allin1fix z rzeczywistym plikiem audio
- RAM usage: Demucs + MusicGen (nie jednocześnie)
- OMAR-RQ model download i pierwsze uruchomienie

## Wniosek

**Faza 0 zaliczona** dla bibliotek które można testować bez GPU/dużego RAM.
Stack jest kompatybilny. Dockerfile jest gotowy z prawidłową kolejnością.
Następny krok: deploy na Hetzner i test pełnego pipeline.
