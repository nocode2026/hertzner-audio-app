# MASTER_CONTEXT.md — Pełna pamięć projektu
# DJ Intro/Outro Generator
# Ostatnia aktualizacja: sesja planowania (przed rozpoczęciem budowania)

> Ten plik czytasz NA POCZĄTKU każdej sesji — zanim cokolwiek zrobisz.
> Zawiera WSZYSTKIE decyzje, DLACZEGO je podjęto, i co nas czeka.
> Przed każdym krokiem: przeczytaj sekcję RYZYKA i PRZEWIDYWANIA.

---

## 1. CEL PROJEKTU

Aplikacja dla DJ-ów która:
1. Przyjmuje piosenkę (MP3/WAV)
2. Wykonuje profesjonalną analizę audio
3. Generuje pasujące intro i outro (3 warianty każde)
4. Pozwala na ręczną korektę w edytorze
5. Eksportuje rozszerzony utwór + cue pointy do Rekordbox/Mixxx

**Dla kogo:** Muzyka klubowa — house, techno, trance, D&B, hip-hop.
**Nie dla:** Jazz, muzyka akustyczna, klasyczna.
**Użytek:** Personal (niekomercyjny) — pozwala używać OMAR-RQ (CC BY-NC-SA 4.0).

---

## 2. DECYZJE STACKU — Z UZASADNIENIEM

### Backend stack (OSTATECZNY):

| Biblioteka | Rola | Dlaczego ta, nie inna |
|-----------|------|-----------------------|
| `allin1fix` | BPM, beats, downbeats, struktura (intro/verse/chorus/drop/outro) | Wytrenowany na Harmonix Set (muzyka klubowa). Naprawia błędy allin1. Obsługuje PyTorch 2.x. Używa `demucs-infer` wewnętrznie — nie koliduje z naszym Demucs. |
| `OMAR-RQ` (wariant multifeature-25hz) | Chord recognition, key detection, pitch | SOTA 2025. MTG Barcelona (ci sami co Essentia). Wytrenowany na 330k godzin muzyki. Lepszy niż Essentia dla akordów i tonacji. CC BY-NC-SA 4.0 = OK dla personal use. |
| `Essentia` | Spektrum, LUFS loudness, stereo width, waveform RGB data | Niezastąpiony dla danych wizualnych (Pixi.js). Spotify/BBC go używają. Uzupełnia OMAR-RQ i allin1fix. |
| `Demucs` (htdemucs) | Stem separation: vocals/drums/bass/melody | Złoty standard. Stemy idą do MusicGen jako audio conditioning. Uruchamiany OSOBNO przed allin1fix (przekazujemy stemy przez --stems-from-dir). |
| `MusicGen` (facebook/musicgen-melody) | Generowanie 3x intro + 3x outro | Jedyna open-source opcja. Kondycjonowanie audio+tekst. Tekst generowany z wyników analizy. |
| `pyrubberband` | Pitch shifting, time stretching | Standard branżowy (używa go Ableton). Bezpieczny zakres: ±2 semitony, ±10% BPM. |
| `pydub` + `ffmpeg` | Sklejanie audio, konwersja formatów | Niezastąpiony. Crossfade 1 bar. |
| `FastAPI` | REST API | Async, szybki, Pydantic validation. |
| `Celery` + `Redis` | Kolejka zadań | Pipeline trwa 30-60 min na CPU — MUSI być async. |

### Frontend stack:
| Tech | Rola | Dlaczego |
|------|------|---------|
| React 18 + TypeScript | UI | Standard. Strict mode — bez `any`. |
| Tailwind CSS | Styling | Szybki development. |
| Pixi.js (WebGL) | RGB Waveform | Jedyna opcja dla Mixxx-style colored waveform w przeglądarce. Canvas API za wolny. |
| axios | HTTP | Standard. |

### Infrastruktura:
- **Backend:** Hetzner CPX41 — 16GB RAM, 4 vCPU (~20€/mies). NIE CPX31 (8GB za mało dla Demucs+MusicGen).
- **Frontend:** Vercel (free tier).
- **Repo:** GitHub.

### Co odrzuciliśmy i dlaczego:
- ❌ `librosa` — zastąpiona przez Essentia (lepsza) + allin1fix
- ❌ `madmom` osobno — wbudowany w allin1fix
- ❌ `allin1` (oryginał) — dependency issues z Python 3.10+
- ❌ `Polymath` — Python <=3.10, nieaktywny od 2023, monolityczny skrypt, gorsze narzędzia
- ❌ `SongFormer` — brak paczki Python, za wcześnie na produkcję
- ❌ OMAR-RQ dla kodu produkcyjnego — CC BY-NC-SA 4.0 (OK dla personal, nie dla commercial)

---

## 3. ARCHITEKTURA SYSTEMU

```
[React Frontend — Vercel]
  Upload → Polling → Dashboard → Edytor → Export
        ↕ REST API (HTTPS)
[FastAPI — Hetzner CPX41]
  /api/upload → Celery Queue → Redis
                    ↓
            [Worker Pipeline — KOLEJNOŚĆ WAŻNA]
            
            Step 1: Konwersja do WAV (ffmpeg)
                    DLACZEGO: MP3 daje 20-40ms offset w allin1fix
                    
            Step 2: Demucs htdemucs (stems)
                    Output: vocals.wav, drums.wav, bass.wav, melody.wav
                    DLACZEGO PIERWSZY: stemy potrzebne zarówno dla analizy jak i MusicGen
                    Czas: ~10-20 min CPU
                    
            Step 3: allin1fix (struktura, beats)
                    Input: oryginalne WAV + stemy z Step 2 (--stems-from-dir)
                    DLACZEGO --stems-from-dir: unikamy podwójnego Demucs
                    Output: BPM, beats, downbeats, segmenty (intro/verse/chorus/drop/outro)
                    
            Step 4: OMAR-RQ multifeature-25hz (harmonia)
                    Input: oryginalne WAV
                    Output: key, mode, chord progression, pitch
                    
            Step 5: Essentia (spektrum + waveform data)
                    Input: oryginalne WAV
                    Output: LUFS, stereo width, brightness, waveform RGB data dla Pixi.js
                    
            Step 6: Generowanie cue pointów
                    Input: wyniki Steps 3+4+5
                    Output: mix_in, mix_out, drop, breakdown, vocal_in, 8bar markers
                    WAŻNE: każdy cue snappowany do najbliższego beatu z allin1fix
                    
            Step 7: MusicGen musicgen-melody (generowanie)
                    Input: drums+bass+melody stems (bez wokali) pierwsze 10s
                    Input: text prompt z analizy (BPM, key, styl, energia)
                    Output: 3x intro WAV + 3x outro WAV
                    Progressive build: drums(8 bars) → +bass(8 bars) → +melody(8 bars)
                    Reverb tail na outro
                    Phrase-quantized: zaokrąglenie do pełnego bara
                    Czas: ~10-15 min per generacja (x6 = 60-90 min)
                    
            Step 8: pyrubberband (korekta pitch/BPM jeśli requested)
                    Tylko gdy user zmienia key/BPM w edytorze
                    
            Step 9: pydub (sklejanie)
                    intro + oryginał + outro z crossfade 1 bar
                    Normalizacja do LUFS oryginału
                    
            Step 10: Export builder
                    MP3 320kbps + WAV 24bit
                    Rekordbox XML
                    Mixxx SQLite
                    Waveform JSON (cache dla frontendu)
```

---

## 4. API ENDPOINTS

```
POST   /api/upload
       Input: multipart/form-data, plik audio max 100MB
       Walidacja: MIME type po stronie serwera (nie tylko rozszerzenie)
       Output: {"job_id": "uuid", "status": "queued"}

GET    /api/status/{job_id}
       Output: {"status": "processing", "progress": 45, "current_step": "musicgen"}
       Polling co 3 sekundy z frontendu

GET    /api/result/{job_id}
       Output: pełne wyniki analizy + linki do plików

POST   /api/reprocess/{job_id}
       Input: {
         trim_start: float,      // sekundy — ucięcie ciszy
         first_beat: float,      // pozycja downbeatu
         key_shift: int,         // semitony (-12 do +12), OSTRZEŻENIE przy >2
         bpm_target: float,      // docelowe BPM, OSTRZEŻENIE przy >10%
         selected_intro: int,    // 0/1/2
         selected_outro: int     // 0/1/2
       }
       Pomija Steps 1-6, zaczyna od Step 7 z poprawkami

GET    /api/download/{job_id}/{file_type}
       file_type: "mp3" | "wav" | "rekordbox" | "mixxx" | "all_zip"
```

---

## 5. FRONTEND — KOMPONENTY

### Upload View
- Drag & drop MP3/WAV/FLAC/AAC
- Walidacja client-side: format + max 100MB
- Konwersja statusu polling na czytelne etapy:
  - 0-10%: "Konwersja audio..."
  - 10-25%: "Separacja stemów (Demucs)..."
  - 25-55%: "Analiza struktury i harmonii..."
  - 55-60%: "Generowanie cue pointów..."
  - 60-95%: "Generowanie intro/outro (AI)..."
  - 95-100%: "Przygotowanie eksportu..."

### Waveform Component (Pixi.js WebGL)
- RGB: czerwony=bass, zielony=mid, niebieski=high
- Beat grid: pionowe linie na każdym beacie
- Phrase markers: pogrubione co 8 barów
- Sekcje kolorowane tłem różnymi kolorami
- Cue point markery (przeciągalne, snap do beat gridu)
- Playback cursor
- Zoom scroll wheel
- Klik = skok do pozycji w playerze
- WZORZEC: buduj sub-krok po sub-kroku (4.3a → 4.3b → itd.)

### Analysis Dashboard
- BPM + Key jako duże liczby
- Camelot wheel (SVG klikalna)
- Timeline struktury
- Krzywa energii (recharts)
- Tabela cue pointów (edytowalna)

### Editor Panel
- Silence trim handle
- Downbeat alignment marker
- Camelot wheel klikalna → zmiana tonacji
- BPM suwak ±10%
- WAŻNE: zmiany → POST /api/reprocess

### Variations Player
- 3 karty intro + 3 karty outro
- Miniaturowy waveform + play/stop per karta
- Radio selection

### Export Panel
- Wybór formatu
- Download ZIP

---

## 6. STRUKTURA FOLDERÓW

```
project/
├── CLAUDE.md              ← instrukcje operacyjne
├── MASTER_CONTEXT.md      ← ten plik (pamięć projektu)
├── BUILD_PLAN.md          ← plan krok po kroku
├── WORK_LOG.md            ← historia sesji
├── KNOWN_ISSUES.md        ← błędy i rozwiązania
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── worker.py
│   │   └── pipeline/
│   │       ├── converter.py      ← Step 1: WAV conversion
│   │       ├── demucs.py         ← Step 2: stems
│   │       ├── allin1fix.py      ← Step 3: structure+beats
│   │       ├── omarrq.py         ← Step 4: harmony
│   │       ├── essentia.py       ← Step 5: spectrum+waveform
│   │       ├── cue_points.py     ← Step 6
│   │       ├── musicgen.py       ← Step 7
│   │       ├── rubberband.py     ← Step 8
│   │       ├── assembler.py      ← Step 9: pydub
│   │       └── exporter.py       ← Step 10
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── requirements.txt
└── frontend/
    └── src/
        ├── components/
        │   ├── Upload/
        │   ├── Waveform/
        │   ├── Dashboard/
        │   ├── Editor/
        │   ├── Variations/
        │   └── Export/
        ├── hooks/
        │   ├── useJobPolling.ts
        │   └── useAudioPlayer.ts
        ├── api/client.ts
        └── types/index.ts
```

---

## 7. RYZYKA — ZNANE I MITYGACJE

### RYZYKO 1: Konflikty zależności (WYSOKIE PRAWDOPODOBIEŃSTWO)
**Problem:** allin1fix używa `demucs-infer`, MusicGen używa `audiocraft`, Essentia ma własne zależności numpy.
**Mitygacja:**
- allin1fix uruchamiamy z `--stems-from-dir` (podajemy stemy z naszego Demucs)
- Sprawdzamy kompatybilność PRZED pisaniem kodu (Faza 0)
- Jeśli konflikt: osobne virtualenvy dla różnych etapów, komunikacja przez pliki
- Plan B: Docker containers per moduł (overhead ale działa)

### RYZYKO 2: RAM na Hetzner CPX41 16GB (ŚREDNIE)
**Problem:** Demucs (htdemucs) ~4GB RAM + MusicGen ~6GB RAM = prawie limit
**Mitygacja:**
- Uruchamiamy Demucs → zwalniamy RAM → uruchamiamy MusicGen (nie jednocześnie)
- `del model; torch.cuda.empty_cache()` po każdym etapie
- Jeśli niewystarczy: Hetzner CCX43 (32GB, ~40€/mies) lub demucs model `htdemucs_ft` (mniejszy)

### RYZYKO 3: MusicGen jakość (ŚREDNIE)
**Problem:** 85% szans na dobry wynik dla muzyki klubowej od razu.
**Mitygacja:**
- 3 warianty = większa szansa że jeden jest dobry
- Iteracja na prompt engineering
- Zaczynamy od prostszych gatunków (techno, minimal house) — bardziej repetytywne

### RYZYKO 4: OMAR-RQ nowy model (NISKIE-ŚREDNIE)
**Problem:** Model z lipca 2025, mało przypadków użycia produkcyjnego.
**Mitygacja:**
- Wariant `multifeature-25hz-fsq` — najlepszy dla chord/key
- Fallback: Essentia key detection jeśli OMAR-RQ zawiedzie
- Testujemy na 5 różnych traczkach przed integracją

### RYZYKO 5: Czas przetwarzania (PEWNE)
**Problem:** 30-90 minut na CPU na pełny pipeline.
**Mitygacja:**
- Celery + Redis daje async UX — user nie czeka przy ekranie
- Progress polling co 3s daje feedback
- Dla v2: GPU server (Hetzner GX, ~0.50€/godz on-demand)

### RYZYKO 6: Rekordbox XML format (ŚREDNIE)
**Problem:** Rekordbox może odrzucić XML jeśli format nie jest dokładny.
**Mitygacja:**
- Testujemy na każdej wersji Rekordboxa (6.x i 7.x)
- Wzorzec XML: `<?xml version="1.0" encoding="UTF-8"?><DJ_PLAYLISTS Version="1.0.0">`
- Fallback: eksport .csv który Rekordbox też akceptuje

---

## 8. PRZEWIDYWANIA — MYŚL DO PRZODU I DO TYŁU

### Problemy które BĘDĄ na pewno (myśl do tyłu):
1. **Pierwsze uruchomienie allin1fix** — będzie błąd instalacji. Rozwiązanie już znane: `--no-build-isolation`
2. **OMAR-RQ model download** — 1.5GB przy pierwszym uruchomieniu. Poczekaj.
3. **Essentia instalacja** — może potrzebować `apt install libsndfile1 libavcodec-dev`
4. **ffmpeg** — musi być w Dockerfile: `apt install ffmpeg`
5. **Waveform Pixi.js** — pierwsze renderowanie będzie szare. RGB wymaga osobnej kalibracji.
6. **MusicGen pierwsze wyniki** — mogą brzmieć generycznie. Prompt engineering potrzebny.

### Co się zmieni gdy będziemy mieć użytkowników (myśl do przodu):
- Licencja OMAR-RQ (CC BY-NC-SA) — przy komercjalizacji trzeba zmienić na Essentia dla key/chord
- Czas przetwarzania — GPU server stanie się koniecznością
- Concurrent users — Celery workers skalujemy horyzontalnie
- Storage — pliki audio zajmują dużo miejsca, potrzebne S3/R2 (Cloudflare)

### Decyzje których NIE podejmujemy teraz (v2):
- Konta użytkowników i auth
- Biblioteka tracków (historia)
- Track compatibility scoring
- Batch processing
- Mobile app
- GPU acceleration

---

## 9. ZASADY BEZPIECZEŃSTWA

- Klucze API przez `.env` — nigdy w kodzie
- `.env` w `.gitignore` — sprawdzaj PRZED każdym commitem
- Upload plików: walidacja MIME server-side, max 100MB
- Pliki użytkownika: UUID jako nazwa, nigdy oryginalna
- Cleanup: Celery task czyści pliki tymczasowe po 24h
- Nie commituj wygenerowanych plików audio

---

## 10. ZASADY WERYFIKACJI

Każdy step MUSI być zweryfikowany konkretnym testem przed przejściem dalej.

**Faza 0 (instalacja):**
```bash
python -c "import allin1fix; import essentia; import audiocraft; print('OK')"
# Musi zwrócić OK bez błędów
```

**Step 2 (Demucs):**
```python
# Sprawdź że 4 pliki WAV istnieją i mają >0 bajtów
```

**Step 3 (allin1fix):**
```python
# BPM w zakresie 60-200, >0 segmentów, >0 beatów
```

**Step 4 (OMAR-RQ):**
```python
# Key w dozwolonym zestawie, chord_progression nie pusty
```

**Step 7 (MusicGen):**
```python
# Każdy plik intro/outro: długość 10000-120000ms
```

**Waveform (Pixi.js):**
```
# Sprawdź wizualnie: czy waveform jest kolorowy (nie szary)?
# Czy beat grid jest wyrównany z transientami?
```

**Cue pointy:**
```python
# Czy mix_in i mix_out istnieją?
# Czy każdy cue jest na pozycji beatu (tolerancja 10ms)?
```

**Rekordbox XML:**
```python
import xml.etree.ElementTree as ET
tree = ET.parse(path)
assert tree.getroot().tag == "DJ_PLAYLISTS"
```

---

## 11. COMMIT MESSAGES — FORMAT

```
feat(demucs): implement stem separation pipeline
fix(allin1fix): handle --stems-from-dir parameter
test(musicgen): verify 3 variants generation
refactor(waveform): add RGB coloring to Pixi.js
```

Nigdy: "fix", "WIP", "update", "changes"

---

## 12. WORK LOG — FORMAT

Po każdej sesji dopisz na górze WORK_LOG.md:

```markdown
## [DATA] — [co zrobiono]

**Faza/Krok:** [np. Faza 0 / Krok 1.1]
**Co zrobiono:** [lista]
**Zmienione pliki:** [ścieżki]
**Weryfikacja:** [jak sprawdzono że działa]
**Status:** zakończone / w toku / błąd
**Następny krok:** [co teraz]
**Uwagi:** [cokolwiek istotnego]
```

---

## 13. KOLEJNOŚĆ FRAZ BUDOWANIA

```
FAZA 0: Test instalacji (1 dzień)
  → Czy wszystkie biblioteki działają razem na Python 3.11?
  → Jeśli nie: rozwiązujemy konflikty PRZED pisaniem kodu

FAZA 1: Infrastruktura Backend (2-3 dni)
  1.1 Docker Compose (api + worker + redis)
  1.2 FastAPI skeleton + health check
  1.3 Celery + Redis test

FAZA 2: Pipeline Audio (5-7 dni)
  2.1 Upload + Job Management
  2.2 Step 1: WAV conversion
  2.3 Step 2: Demucs stems
  2.4 Step 3: allin1fix (--stems-from-dir)
  2.5 Step 4: OMAR-RQ harmony
  2.6 Step 5: Essentia spectrum+waveform
  2.7 Step 6: Cue points
  2.8 Step 7: MusicGen generation
  2.9 Step 8: pyrubberband
  2.10 Step 9+10: Assembly + Export

FAZA 3: Integracja Celery (1-2 dni)
  3.1 Główny task z progress updates
  3.2 Reprocess endpoint

FAZA 4: Frontend (7-10 dni)
  4.1 Setup + typy
  4.2 Upload + polling
  4.3 Waveform Pixi.js (sub-krok po sub-kroku!)
  4.4 Dashboard
  4.5 Editor
  4.6 Variations Player
  4.7 Export

FAZA 5: Deployment
  5.1 Hetzner setup
  5.2 Vercel deploy
  5.3 End-to-end test z prawdziwym trackiem
```

---

## 14. TESTTRACKI DO WERYFIKACJI

Wybierz tracki które DOBRZE przetestują edge cases:
1. **Techno 128 BPM** — standard, powinien działać najlepiej
2. **Deep house 120 BPM** — wolniejsze tempo
3. **Drum & Bass 174 BPM** — szybkie tempo, test BPM detection
4. **Track z BPM shift** — test stability detection
5. **Track z długim intro** — test segmentacji

Testy od Step 2 (Demucs) wykonuj na tym samym pliku WAV przez wszystkie etapy.
