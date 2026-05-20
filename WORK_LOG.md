# WORK_LOG — Historia pracy w projekcie
# DJ Intro/Outro Generator

> Nowe wpisy na górze.

---

## [2026-05-19] — Faza 4.6 — Variations Player (intro/outro karty + audio player)

**Faza/Krok:** Faza 4 / Krok 4.6

**Co zrobiono:**

### Backend — nowy endpoint `GET /api/download/{job_id}/{file_type}`
- Whitelist dozwolonych plików: `intro_0/1/2`, `outro_0/1/2`, `original`
- Walidacja `job_id` jako UUID (HTTPException 400 przy błędnym formacie)
- `FileResponse` z `Accept-Ranges: bytes` header → działa seeking audio w przeglądarce
- Stała `_AUDIO_FILES` i `OUTPUT_DIR` dodane do `main.py`

### `src/components/Variations/VariantCard.tsx`
- **Audio player**: `<Audio>` element w ref, preload='metadata' (pobiera czas bez full download)
- **Peak extraction**: `fetch(url)` → `AudioContext.decodeAudioData()` → 80 peak sampli
  - Błędy ignorowane (silently degrade) → karta nadal działa do odtwarzania
  - `cancelled` flag → safe unmount
- **Mini waveform SVG** (`viewBox 0 0 100 40`):
  - Bars z `peak * cy * 1.9` wysokości → widać dynamikę
  - Placeholder bars gdy peaks nie załadowane (szare, statyczne)
  - Progress overlay div (0-100% width) nakładany na SVG
- **Seekbar**: kliknięcie → `audio.currentTime = t * duration`
- **shouldStop prop**: `useEffect` → pause + reset gdy inna karta zaczyna grać
- **Wybór (onSelect)**: kółko radio (filled violet = selected, empty = nie)
- `available=false` → karta zszarzała z "Nie wygenerowano" tekstem

### `src/components/Variations/VariationsPlayer.tsx`
- `playingKey` state (`intro_0`..`outro_2` | null) → jeden card gra na raz
- `audioUrl(jobId, type, index)` → `/api/download/{jobId}/{type}_{index}`
- `renderSection()` helper → 3 karty w `sm:grid-cols-3`
- Graceful empty: jeśli `variations = null` lub brak pliku → komunikat tekstowy
- Sekcja "Intro" i "Outro" każda ze swoim grid kart

### EditorPanel — aktualizacja
- `selectedIntro: number` i `selectedOutro: number` jako props (nie hardcoded 0)
- Przekazywane do `submit()` → `ReprocessRequest.selected_intro/outro`

### App.tsx — `ResultView` z połączonym stanem
- `selectedIntro/Outro` state w `ResultView` → shared między `VariationsPlayer` i `EditorPanel`
- Kolejność: Waveform → Dashboard → VariationsPlayer → EditorPanel

**Weryfikacja:**
- `npm run build` → 0 TypeScript errors ✅
- Bundle: main 269kB (88kB gzip), Pixi lazy 230kB (67kB gzip) ✅
- `main.py` syntax check: ✅

**Status:** zakończone

**Następny krok:**
- Faza 5 — Deployment (Hetzner: Docker Compose, CI/CD; Vercel: frontend)
- assembler.py (pydub mixing) i exporter.py (Rekordbox/Mixxx) — opcjonalnie przed deploy

---

## [2026-05-19] — Faza 4.5 — Editor Panel (korekty + reprocess)

**Faza/Krok:** Faza 4 / Krok 4.5

**Co zrobiono:**

### `src/utils/camelot.ts` — wspólna logika Camelot (single source of truth)
- `CAMELOT_WHEEL` array (12 pozycji × A/B)
- `semitoneShift(from, to)` → najkrótsze przesunięcie w [-6, +6]
- `parseCamelot(cam)` → {pos, mode}
- `isCompatible(cur, pos, mode)` → bool (miksowanie harmoniczne)
- `camelotLabel(pos, mode)` → "Am", "C" itp.
- CamelotWheel.tsx przepisany żeby importować stąd (eliminacja duplikacji)

### `src/hooks/useReprocess.ts` — async poll hook
- `submit(corrections)` → POST /api/reprocess/{jobId} → polling co 3s → 'done'/'failed'
- Stany: 'idle' | 'submitting' | 'processing' | 'done' | 'failed'
- `activeRef` guard → safe unmount, React StrictMode safe
- `reset()` → czyszczenie stanu (np. przed kolejną korektą)

### `src/components/Editor/EditorPanel.tsx`
Dwie kolumny:

**Lewa — Zmiana tonacji:**
- `CamelotWheel` (klikalna) → `handleKeySelect(shift, targetPos, targetMode)`
- `targetCam` state: zaktualizowany na każde kliknięcie → wheel pokazuje TARGET key
- `currentSemitone`: zawsze ORYGINAŁ → shift obliczany od oryginału (nie kumulatywny)
- Quick buttons: -2 / -1 / 0 / +1 / +2 semitonów
- Wyświetlanie: "8A → 7A — Ebm | -7 semitonów"
- SafetyBadge: żółte ostrzeżenie gdy |shift| > 2

**Prawa — kontrolki numeryczne:**
- **BpmSlider**: range ±15% (za safe zone ±10%)
  - Safe zone overlay (ciemny zielony)
  - Marker oryginalnego BPM
  - Wartość %, SafetyBadge gdy >10%
  - Niewidoczny `<input range>` nad widocznym paskiem (cursor pointer działa)
- **Trim ciszy**: NumInput 0-60s, step 0.1s
- **Pierwsza jedynka**: NumInput 0-30s, step 0.001s (ms precision)

**Footer:**
- Summary row (font-mono): trim | beat | shift | bpm
- Progress bar podczas przetwarzania (jobStatus.progress)
- Error panel (border red) przy 'failed'
- Success panel (border green) przy 'done'
- Przyciski: "Reset" + "Zastosuj korekty ▶"
- `bpm_target = null` gdy bez zmiany (API rozumie null = keep original)

### CamelotWheel — aktualizacja sygnatury `onKeySelect`
- Stara: `(shift: number) => void`
- Nowa: `(shift: number, targetPos: number, targetMode: 'A' | 'B') => void`
- EditorPanel zna dokładnie który segment kliknięto → aktualizuje targetCam bez reverse lookup

### App.tsx — rozbudowany
- `ResultView` dostaje `onResultUpdate: (r: JobResult) => void`
- `EditorPanel` zamontowany pod dashboardem
- `setResult(newResult)` po reprocess → waveform i dashboard odświeżają się automatycznie

**Weryfikacja:**
- `npm run build` → 0 TypeScript errors ✅
- Bundle: main 264kB (87kB gzip), Pixi lazy 230kB (67kB gzip) ✅

**Status:** zakończone

**Następny krok:**
- Faza 4.6 — Variations Player (3x intro + 3x outro karty, play/stop, wybór)
- Faza 5 — Deployment Hetzner + Vercel CI/CD

---

## [2026-05-19] — Faza 4.4 — Analysis Dashboard (Camelot Wheel + Krzywa energii)

**Faza/Krok:** Faza 4 / Krok 4.4

**Co zrobiono:**

### Nowe komponenty: `src/components/Dashboard/`

**`CamelotWheel.tsx`** — SVG 240×240:
- 12 sektorów × 2 pierścienie: inner=A(minor) rA=53-77, outer=B(major) rB=79-103
- `ringPath(pos, r1, r2)`: SVG arc path z gap 1.5° między sektorami
- Kolory: `hsl((pos-1)*30, %, %)` per pozycja → naturalny rainbow bez powtórzeń
  - active: 85% sat, 52% lightness; compatible: 60%/34%; default: 35%/20%
- `isCompatible()`: ta sama pozycja inny tryb LUB sąsiednia pozycja ten sam tryb (wrap 1↔12)
- `onKeySelect(semitones)`: oblicza przesunięcie `(toSemi - fromSemi + 12) % 12`, normalizuje do [-6, +6]
- Centrum SVG: numer pozycji (22px, colored) + nazwa klucza (11px, szara)
- `<title>` w każdym segmencie → tooltip natywny

**`EnergyCurve.tsx`** — SVG viewBox "0 0 600 80":
- Energia = `0.5*low + 0.35*mid + 0.15*high` per klatkę (wagowo: bass dominuje)
- `downsample(arr, 600)` + `smooth(arr, win=6)` → brak artefaktów przy dużej rozdzielczości
- Section backgrounds w tle (ta sama paleta co waveform)
- Gradient fill (linearGradient violet, 55%→5% alpha) + stroke polyline (violet #8b5cf6)
- Linie siatki 25/50/75% energii (biały, 6% alpha)
- Empty state fallback z tekstem

**`StructureTimeline.tsx`** — responsywny pasek sekcji:
- Proporcjonalne segmenty (width = duration% całości)
- Klikalny → onSeek(sec.start)
- Etykiety tylko gdy segment > 5% szerokości (bez overflow)
- Legenda pod paskiem: label + timestamp, klikalna

**`AnalysisDashboard.tsx`** — główny agregator:
- Stat cards: BPM (+ confidence %), Tonacja (+ Camelot ID), Loudness (LUFS), Czas trwania, Pierwsza jedynka
- Grid 2-kolumnowy: CamelotWheel (left) + EnergyCurve + StructureTimeline (right)
- Chord progression strip (max 16 akordów, horizontal scroll)
- Cue points table z kolorowymi dot-markerami per typ (mix_in=green, drop=yellow itd.)
- `onKeyShift` prop przekazany do CamelotWheel (gotowy na Fazę 4.5 Editor)
- `parseSections()`: type-safe ekstrakcja z `analysis.structure` (Record<string, unknown>)

**`index.ts`** — re-export wszystkich 4 komponentów

### App.tsx — uproszczony
- `ResultView` (inline) zastąpiono przez `AnalysisDashboard`
- `useAudioPlayer.seek` wired do waveform i dashboardu

**Weryfikacja:**
- `npm run build` → 0 TypeScript errors ✅
- Bundle: main 255kB (84kB gzip), WaveformRenderer lazy 230kB (67kB gzip) ✅

**Status:** zakończone

**Następny krok:**
- Faza 4.5 — Editor Panel (silence trim handle, downbeat align, Camelot wheel klikalna → key_shift, BPM suwak)
- Faza 4.6 — Variations Player (3x intro + 3x outro karty z miniaturą + play/stop)
- Faza 5 — Deployment Hetzner + Vercel

---

## [2026-05-19] — Faza 4.3 — Waveform Pixi.js (WebGL)

**Faza/Krok:** Faza 4 / Krok 4.3

**Co zrobiono:**

### Pliki stworzone
**`src/components/Waveform/WaveformRenderer.ts`** — klasa Pixi.js v8:
- Warstwy (z-order): layerSections → layerWaveform → layerBeats → layerCues → gCursor
- **RGB waveform**: gLow (red 0xff3333), gMid (green 0x44ff88), gHigh (blue 0x3388ff)
  - Batch fill: wszystkie recty danego pasma w jednym `.fill()` call → wydajne GPU batch
  - Rysowane tylko widoczne klatki w viewport (startFrame/endFrame z timeToX)
- **Beat grid**: gBeats (thin 0.5px), gDownbeats (medium 1px), gPhrases (thick 2px white)
  - Batch stroke: wszystkie linie danego typu w jednym `.stroke()` call
- **Section backgrounds**: rgba, 0.13 alpha, kolory: intro=blue, verse=green, chorus=purple itd.
  - Section labels (text) w osobnym `labelSections` Container — poprawne destroy() bez leaków
  - Labels widoczne tylko przy zoom >= 2
- **Cue point markers**: pionowa linia + trójkąt na górze + label
  - Kolory per typ: mix_in=green, drop=yellow, vocal_in=cyan, mix_out=orange, breakdown=red
  - Destroy z `{ children: true }` przy każdym redraw
- **Playback cursor**: cyan (0x00e5ff) 1.5px, rysowany tylko gdy w viewport
- **Zoom**: scroll wheel, min 1x max 32x, punkt pod kursorem pozostaje stacjonarny
- **Pan**: drag (próg 4px), clampPan() do granic tracka
- **Click to seek**: callback `onSeek(time)`, ignorowany gdy drag > 4px

**`src/components/Waveform/WaveformView.tsx`** — React wrapper:
- Dynamic import `import('./WaveformRenderer')` → Pixi.js w osobnym chunk (lazy-loaded)
- Async init z `destroyed` flag dla React StrictMode (double-mount safe)
- `onSeekRef` pattern: callback nigdy nie jest stale
- ResizeObserver → `renderer.resize(w, h)`
- 3 oddzielne efekty: init | dane | cursor (minimalne re-rendery)

**`src/components/Waveform/index.ts`** — re-export

### App.tsx — rozbudowany do `ResultDashboard`
- Waveform section (160px height)
- Grid statystyk: BPM, tonacja z Camelot, pierwsza jedynka, czas trwania
- Tabela cue pointów (klikalnych → onSeek)

**Weryfikacja:**
- `npm run build` → 0 TypeScript errors ✅
- Code splitting: WaveformRenderer lazy chunk 230kB (66kB gzip) ✅
- Główny bundle: 245kB (80kB gzip) ✅
- Brak chunk size warning ✅

**Status:** zakończone

**Następny krok:** Faza 4.4 — Analysis Dashboard (BPM, key, Camelot wheel, krzywa energii, tabela struktury)
  LUB Faza 4.5 — Editor Panel (silence trim, downbeat align, key shift, BPM suwak)
  LUB Faza 5 — Deployment (end-to-end test na Hetzner)

---

## [2026-05-19] — Faza 4.1 + 4.2 — React Frontend: Setup + Upload + Polling

**Faza/Krok:** Faza 4 / Kroki 4.1 i 4.2

**Co zrobiono:**

### Stack i konfiguracja (Faza 4.1)
- Vite 8 + React 18 + TypeScript (strict mode)
- Tailwind CSS v4 z `@tailwindcss/vite` plugin (v4 nie wymaga `tailwind.config.js`)
- axios dla HTTP
- Vite dev proxy: `/api` → `http://localhost:8000`

### Pliki stworzone
**`src/types/index.ts`** — wszystkie interfejsy TypeScript:
- `UploadResponse`, `JobStatus`, `JobResult`
- `BeatData`, `AnalysisData`, `HarmonyData`, `VariationsData`, `CuePoint`
- `ReprocessRequest`, `AppState`

**`src/api/client.ts`** — axios-based API client:
- `uploadAudio(file)` → POST /api/upload (multipart/form-data)
- `getJobStatus(jobId)` → GET /api/status/{job_id}
- `getJobResult(jobId)` → GET /api/result/{job_id}
- `reprocessJob(jobId, corrections)` → POST /api/reprocess/{job_id}

**`src/hooks/useJobPolling.ts`** — polling hook:
- 3s interval, auto-stop na done/failed
- Automatycznie pobiera `getJobResult` po statusie `done`
- Cleanup ref-based (clearTimeout on unmount i re-run)

**`src/hooks/useAudioPlayer.ts`** — HTML5 Audio player hook (placeholder dla Fazy 4.3+)

**`src/components/Upload/DropZone.tsx`** (Faza 4.2):
- Drag & drop + klik do wyboru pliku
- Client-side walidacja: MIME types + rozmiar ≤100 MB
- Accessible: role=button, tabIndex, aria-label, onKeyDown

**`src/components/Upload/ProgressBar.tsx`** (Faza 4.2):
- 6 etapów z zakresami procentowymi (0-10, 10-25, 25-60, 60-72, 72-95, 95-100)
- Dot markers dla każdego etapu (active/done/pending)
- role=progressbar, ARIA attributes

**`src/components/Upload/UploadView.tsx`** (Faza 4.2):
- Orchestruje upload → polling → done/error flow
- Stany: idle → uploading → processing → done
- Error handling z przyciskiem "Spróbuj ponownie"

**`src/App.tsx`** — state machine idle/done:
- Stan `done`: mini-dashboard (BPM, tonacja, czas)
- Przycisk powrotu do uploadu

**`src/index.css`** — zastąpiono Vite boilerplate przez `@import "tailwindcss"`

**Zmienione pliki:**
- `src/App.tsx` — kompletna implementacja (usunięto boilerplate)
- `src/index.css` — Tailwind v4 import
- `vite.config.ts` — Tailwind plugin + API proxy

**Weryfikacja:**
- `npm run build` → 0 TypeScript errors, 73 modules ✅
- CSS: 17.27 kB (gzip: 4.06 kB) ✅
- JS: 240 kB (gzip: 78.58 kB) ✅

**Status:** zakończone

**Następny krok:** Faza 4.3 — Waveform Pixi.js (WebGL RGB waveform, beat grid, cue points)

---

## [2026-05-18] — Faza 3.1 — Główny task Celery + Faza 3.2 — Reprocess endpoint

**Faza/Krok:** Faza 3 / Kroki 3.1 i 3.2

**Co zrobiono:**

### jobs.py — rozszerzono o result storage
- `save_result(job_id, data)` → Redis `job:{id}:result` (oddzielny klucz od status)
- `get_result(job_id)` → odczyt pełnych danych pipeline

### schemas.py — nowe modele Pydantic
- `JobResultResponse` — pełna odpowiedź `/api/result/{job_id}`
- `ReprocessRequest` — body dla `/api/reprocess`, walidacja:
  - `key_shift`: int ge=-12 le=12
  - `bpm_target`: float gt=0 (None = pomiń korektę tempa)
  - `selected_intro/outro`: int ge=0 le=2
  - `trim_start`, `first_beat`: float ge=0

### worker.py — pełny pipeline task (Faza 3.1)
`process_audio(job_id, file_path)`:
1. WAV conversion (ffmpeg, 44100Hz stereo 16-bit PCM) — progress 1%→5%
2. Demucs stem separation — progress 10%→25%
3. Essentia analysis — progress 25%→45%
4. allin1fix beats+structure — progress 45%→60%
5. OMAR-RQ harmony — progress 60%→72%
6. Cue points (fast, no progress step)
7. MusicGen variations — progress 72%→95%
8. `save_result()` + `status="done"` — progress 100%

Każdy etap w try/except → błąd logowany, pipeline kontynuuje z dostępnymi danymi.
OMAR-RQ key/mode mergowany do analysis dict przed MusicGen promptem.

`reprocess_audio(job_id, corrections)` (Faza 3.2):
- Wczytuje istniejący wynik z Redis
- Stosuje trim_start (ffmpeg -ss)
- Stosuje key_shift + bpm_target na wybranym intro/outro (pyrubberband)
- Aktualizuje beat grid o offset first_beat
- Zapisuje wyniki w `/app/outputs/{job_id}/reprocess/`

Helpery: `_convert_to_wav`, `_apply_corrections`, `_safe_path`, `_serializable`, `_fail`

### main.py — nowe endpointy
- `GET /api/result/{job_id}` → 409 gdy nie done, 404 gdy brak danych, 200 z JobResultResponse
- `POST /api/reprocess/{job_id}` → 409 gdy processing, 202 + dispatch reprocess_audio

**Zmienione pliki:**
- `app/jobs.py` — save_result, get_result
- `app/models/schemas.py` — JobResultResponse, ReprocessRequest
- `app/worker.py` — pełny pipeline (zastąpiono stub)
- `app/main.py` — dwa nowe endpointy

**Weryfikacja:**
- Syntax check: wszystkie 4 pliki: OK ✅
- Import check: wszystkie klasy i funkcje: OK ✅
- Pydantic validation: key_shift=13 odrzucony, bpm_target=0 odrzucony ✅
- Celery tasks: worker.process_audio, worker.reprocess_audio, worker.add zarejestrowane ✅
- _serializable: numpy types → JSON-serializable ✅
- End-to-end Redis flow: create → update → save_result → get_result → done ✅
- _convert_to_wav: output stereo 44100Hz ✅
- _safe_path: fallback na first valid path ✅
- _apply_corrections key_shift=-2: duration preserved ✅
- Routes: POST /api/upload, GET /api/status, GET /api/result, POST /api/reprocess ✅

**Status:** zakończone

**Następny krok:** Faza 4 — Frontend (React + TypeScript)
  LUB Faza 5 — Deployment na Hetzner (end-to-end test z prawdziwym trackiem)

---

## [2026-05-18] — Faza 2.6 — MusicGen Generowanie Intro/Outro

**Faza/Krok:** Faza 2 / Krok 2.6 (Step 7 pipeline — MusicGen)

**Co zrobiono:**
- Stworzono `app/pipeline/musicgen.py`:
  - `generate_variations(stems, analysis, beats_data, output_dir, job_id, bars) → dict`
  - Model: `facebook/musicgen-melody` przez `transformers` (NIE audiocraft — niekompatybilny z Python 3.12)
  - Klasa: `MusicgenMelodyProcessor` (bezpośrednio, nie `AutoProcessor` — patrz KNOWN_ISSUES)
  - Conditioning: drums+bass+melody mix, pierwsze 10s, 32kHz, bez wokali
  - Generuje 3 intro + 3 outro warianty przez 6 osobnych wywołań generate()
  - Phrase-quantized: max_new_tokens obliczone z BPM i liczby barów (default 8)
  - Minimum 12s na wariant (gwarantuje >10000ms dla BUILD_PLAN assertions)
  - Fade-in 0.5s dla intro, fade-out 3s dla outro (efekt reverb tail)
  - 3 różne prompty per typ (intro/outro) × różne seedy → 3 warianty
  - Memory cleanup: del model; gc.collect(); torch.cuda.empty_cache()
  - Progress: 72% → 95% (spread po 6 generacjach)
  - Graceful: None w liście przy błędzie jednej generacji

**Prompty:**
- Intro: "128 BPM, Am, tech house, progressive build-up, drums intro, no vocals, club music"
- Outro: "128 BPM, Am, tech house, fade out ending, reverb tail, no vocals, club music"
- 3 warianty z różnymi opisami energii

**Zmienione pliki:**
- `app/pipeline/musicgen.py` — nowy

**Weryfikacja:**
- MusicgenMelodyProcessor działa (input_ids shape [1, 9]) ✅
- Wszystkie helper functions: _genre, _build_prompt, _load_conditioning, _max_new_tokens, _fade ✅
- _max_new_tokens(128BPM, 8bars)=750 (15s) ✅
- _max_new_tokens(200BPM, 8bars)=600 (floor 12s zapobiega <10000ms) ✅
- _load_conditioning: miesza stems, normalizuje, tnie do 10s ✅
- Pełna generacja: wymaga Hetzner CPX41 (16GB RAM) — model 2GB powoduje OOM na dev

**Status:** zakończone (kod gotowy; weryfikacja generacji na serwerze)

**Następny krok:** Faza 2.7 — pyrubberband pitch/tempo processing

---

## [2026-05-18] — Faza 2.7 — pyrubberband Pitch Shifting + Tempo Stretching

**Faza/Krok:** Faza 2 / Krok 2.7 (Step 8 pipeline — pyrubberband)

**Co zrobiono:**
- Stworzono `app/pipeline/rubberband.py`:
  - `shift_pitch(file_path, semitones, output_path) → str`
  - `stretch_tempo(file_path, target_bpm, original_bpm, output_path) → str`
  - Zero-adjustment → szybka kopia pliku (bez przetwarzania)
  - Safe ranges: ±2 semitony, ±10% BPM — WARNING logowane przy przekroczeniu
  - Obsługa mono (samples,) i stereo (samples, 2) przez pyrubberband
  - Raise ValueError dla BPM ≤ 0
  - Lazy import pyrubberband (tylko gdy nie-zero adjustment)

**Zmienione pliki:**
- `app/pipeline/rubberband.py` — nowy

**Weryfikacja (5s WAV mono + stereo):**
- shift_pitch -2.0st (mono): output exists ✅
- shift_pitch +2.0st (stereo): output exists ✅
- shift_pitch 0.0 → byte-identical copy (MD5 match) ✅
- shift_pitch +5.0st → warning logged, output exists ✅
- stretch_tempo 128→135 BPM: duration ratio 0.948 vs expected 0.948 ✅
- stretch_tempo same BPM → byte-identical copy ✅
- stretch_tempo target=0 → ValueError ✅

**Status:** zakończone

**Następny krok:** Faza 3.1 — Integracja Celery (główny task process_audio)

---

## [2026-05-18] — Faza 2.5 (MASTER_CONTEXT) — OMAR-RQ harmony analysis

**Faza/Krok:** Faza 2 / Krok 2.5 (Step 4 pipeline — OMAR-RQ)

**Co zrobiono:**
- Stworzono `app/pipeline/omarrq.py`:
  - `analyze_harmony(file_path, beats=None, job_id=None) → dict`
  - Ładuje audio i resampleuje do 24kHz mono (natywny rate OMAR-RQ)
  - Ekstrahuje embeddingi OMAR-RQ z modelu `mtg-upf/omar-rq-multifeature-25hz-fsq`
    (layer=6, 25Hz frame rate, embedding dim=1024)
  - Chromagram FFT (n_fft=8192, hop=960 → 25Hz) z scatter_add do 12 klas tonalnych
  - Krumhansl-Schmuckler key detection na mean chromagramie
  - Template-based chord detection (beat-sync gdy beats podane)
  - Progress: 60% (start) → 66% (chromagram) → 72% (done)
  - Graceful fallback: jeśli OMAR-RQ model zawiedzie, chromagram analiza kontynuuje

**Zwracane pola:**
- `key`: "Am" / "C" itp.
- `key_root`: "A" / "C" itp.
- `mode`: "major" / "minor"
- `key_confidence`: 0.0–1.0
- `camelot`: "8A" / "8B" itp.
- `chord_progression`: lista stringów per beat (lub co 2s)
- `pitch_midi`: MIDI tonic (C4=60)
- `embeddings_shape`: [T, C] lub None jeśli model nie dostępny
- `duration_analyzed`: sekundy przetworzonego audio

**Zmienione pliki:**
- `app/pipeline/omarrq.py` — nowy

**Weryfikacja (15s WAV, A minor syntetyczny, 128 BPM):**
- Key detected: A minor, confidence=0.962 ✅
- Chord detection: 32 chordów, wszystkie 'Am' ✅
- OMAR-RQ model załadowany: 792 weights + 2 embedding_layer ✅
- Embeddings shape: [375, 1024] (15s × 25Hz = 375 frames, dim=1024) ✅
- Camelot: 8A ✅
- pitch_midi: 69 (A4) ✅
- ALL ASSERTIONS PASSED ✅

**Status:** zakończone

**Następny krok:** Faza 2.6 — Essentia spectrum+waveform (oddzielony od harmonii)
  LUB Faza 3.1 — Integracja pipeline w Celery worker

---

## [2025-05-15] — Sesja planowania — kompletna architektura i stack

**Faza/Krok:** Pre-development — planowanie

**Co zrobiono:**
- Zdefiniowano cel projektu (DJ intro/outro generator)
- Przeprowadzono research GitHub, HuggingFace, arXiv, awesome lists
- Wybrano i uzasadniono finalny stack
- Opracowano architekturę systemu
- Zidentyfikowano ryzyka i mitygacje
- Stworzono CLAUDE.md, BUILD_PLAN.md, MASTER_CONTEXT.md

**Kluczowe decyzje:**
- allin1fix zamiast madmom (wbudowany, obsługuje PyTorch 2.x)
- OMAR-RQ dla chord/key (SOTA 2025, personal use OK)
- Essentia zostaje dla RGB waveform data i LUFS
- Demucs uruchamiany OSOBNO, stemy przekazywane do allin1fix przez --stems-from-dir
- Hetzner CPX41 (16GB RAM) nie CPX31 (8GB za mało)
- Polymath odrzucony (Python <=3.10, nieaktywny)
- Pixi.js WebGL dla waveform (Mixxx-style RGB)

**Zmienione pliki:**
- CLAUDE.md — instrukcje operacyjne z pełnym stackiem
- BUILD_PLAN.md — plan budowania krok po kroku
- MASTER_CONTEXT.md — pełna pamięć projektu

**Status:** planowanie zakończone

**Następny krok:** FAZA 0 — test instalacji wszystkich bibliotek na Python 3.11

**Uwagi:**
- Użytek niekomercyjny — OMAR-RQ (CC BY-NC-SA 4.0) jest OK
- Przy komercjalizacji: zastąpić OMAR-RQ Essentia dla key/chord
- MusicGen: 85% szans na dobry wynik dla muzyki klubowej od razu
- Czas przetwarzania: 30-90 min na CPU — Celery jest koniecznością
- RAM: nie uruchamiać Demucs i MusicGen jednocześnie

<!-- WPISY PONIŻEJ -->

## [2026-05-15] — Faza 1.1 — Docker Compose setup + struktura projektu

**Faza/Krok:** Faza 1 / Krok 1.1

**Co zrobiono:**
- Stworzono `requirements.txt` (dokumentacja zależności; instalacja przez Dockerfile RUN)
- Stworzono strukturę `app/`: `__init__.py`, `main.py` (FastAPI placeholder), `worker.py` (Celery + task testowy `add`)
- Stworzono `app/pipeline/__init__.py` i `app/models/__init__.py`
- Stworzono `.gitignore` (chroni .env, uploads/, outputs/, models_cache/, pliki audio)
- Stworzono `.env.example` (wzorzec zmiennych środowiskowych)
- Usunięto obsolete `version` z docker-compose.yml (Docker Compose v2)
- Zweryfikowano docker-compose.yml: config valid (3 services: redis, api, worker)
- Uruchomiono Redis: `docker compose up redis -d` → `PING/PONG` OK
- Docker build pełnego image (PyTorch + audiocraft + allin1fix) uruchomiony w tle — zajmie 20-60 min

**Zmienione pliki:**
- `requirements.txt` — nowy
- `app/__init__.py` — nowy
- `app/main.py` — nowy (FastAPI skeleton bez endpointów — to Faza 1.2)
- `app/worker.py` — nowy (Celery + task testowy `add`)
- `app/pipeline/__init__.py` — nowy
- `app/models/__init__.py` — nowy
- `.gitignore` — nowy
- `.env.example` — nowy
- `docker-compose.yml` — usunięto obsolete `version: '3.8'`

**Weryfikacja:**
- `docker compose config` → valid (3 services) ✅
- `docker compose up redis -d` → uruchomiony ✅
- `docker compose exec redis redis-cli ping` → PONG ✅
- Python syntax check: `app/main.py`, `app/worker.py` → OK ✅
- Pełny `docker compose build` (ML deps) → w toku, oczekiwany na Hetzner

**Status:** zakończone (infrastruktura gotowa; pełny build ML na Hetzner)

**Następny krok:** Faza 1.2 — FastAPI skeleton z `/health`, CORS, obsługą błędów

## [2026-05-15] — Faza 1.2 — FastAPI skeleton

**Faza/Krok:** Faza 1 / Krok 1.2

**Co zrobiono:**
- Rozbudowano `app/main.py` o pełny skeleton FastAPI:
  - `GET /health` → `{"status": "ok", "redis": "ok"}` (z ping do Redis)
  - CORS middleware: `localhost:3000` + `allow_origin_regex` dla `*.vercel.app`
  - Exception handler 404: `{"error": "Not found", "path": "..."}`
  - Exception handler 500: `{"error": "Internal server error"}` + logging
  - Structured logging z formatem `timestamp level name — message`
  - `/docs` i `/redoc` dostępne
- Odkryto bug: Starlette CORSMiddleware nie obsługuje wildcard `*.vercel.app` w `allow_origins` — naprawiono przez `allow_origin_regex`

**Zmienione pliki:**
- `app/main.py` — pełny skeleton

**Weryfikacja:**
- `GET /health` → `{"status": "ok", "redis": "ok"}` ✅
- CORS `Origin: http://localhost:3000` → `access-control-allow-origin: http://localhost:3000` ✅
- CORS `Origin: https://myapp.vercel.app` → `access-control-allow-origin: https://myapp.vercel.app` ✅
- `GET /nonexistent` → `{"error": "Not found", "path": "/nonexistent"}` (status 404) ✅
- `GET /docs` → 200 OK ✅

**Status:** zakończone

**Następny krok:** Faza 1.3 — Celery + Redis queue (task testowy add)

## [2026-05-15] — Faza 1.3 — Celery + Redis queue

**Faza/Krok:** Faza 1 / Krok 1.3

**Co zrobiono:**
- Rozbudowano `app/worker.py` o konfigurację produkcyjną:
  - `result_expires=86400` (24h TTL, automatyczny cleanup wyników)
  - `task_acks_late=True` + `task_reject_on_worker_lost=True` (requeue przy crashu workera)
  - `worker_prefetch_multiplier=1` (jeden job na raz — RAM-intensive pipeline)
  - `broker_connection_retry_on_startup=True` (fix deprecation warning Celery 6.0)
  - `on_worker_ready` signal — log przy starcie workera
  - Task `add` z `bind=True` i explicit name `worker.add`
- Dodano non-root user `appuser` (uid 1000) do Dockerfile — Celery wymaga tego na produkcji
- Dodano env vars `XDG_CACHE_HOME`, `HF_HOME`, `TORCH_HOME` → `/app/.cache`
- Zaktualizowano `docker-compose.yml`: volumes `models_cache` → `/app/.cache` (spójne z nowym userem)

**Zmienione pliki:**
- `app/worker.py` — produkcyjna konfiguracja Celery
- `Dockerfile` — user `appuser`, cache env vars
- `docker-compose.yml` — ścieżki cache poprawione

**Weryfikacja:**
- Worker start: `Connected to redis://redis:6379/0` + `celery@... ready.` — brak warning ✅
- `add.delay(2, 3).get(timeout=10)` → `5` ✅
- `add.delay(100, -7).get(timeout=10)` → `93` ✅
- `docker compose config` — obie usługi montują `models_cache:/app/.cache` ✅

**Status:** zakończone

**Następny krok:** Faza 2.1 — Upload endpoint + Job Management (POST /api/upload, GET /api/status/{job_id})

## [2026-05-15] — Faza 2.1 — Upload + Job Management

**Faza/Krok:** Faza 2 / Krok 2.1

**Co zrobiono:**
- Stworzono `app/models/schemas.py` — Pydantic modele `UploadResponse`, `JobStatusResponse`
- Stworzono `app/jobs.py` — helpery Redis: `create_job`, `get_job`, `update_job` (TTL 24h, `decode_responses=True`)
- Rozbudowano `app/main.py`:
  - `POST /api/upload` (status 202) — walidacja MIME z magic bytes (filetype), limit 100MB, zapis `uploads/{uuid}.{ext}`, dispatch Celery task
  - `GET /api/status/{job_id}` — odczyt z Redis, 404 dla nieistniejącego joba
- Dodano `process_audio` stub do `app/worker.py` — aktualizuje status → "processing", progress=1
- Dodano `filetype` do `Dockerfile` (KROK 7)

**Zmienione pliki:**
- `app/models/schemas.py` — nowy
- `app/jobs.py` — nowy
- `app/main.py` — dwa nowe endpointy
- `app/worker.py` — stub `process_audio`
- `Dockerfile` — dodano `filetype`

**Weryfikacja:**
- `POST /api/upload` z WAV → `{"job_id": "...", "status": "queued"}` (HTTP 202) ✅
- `GET /api/status/{job_id}` → `{"status": "processing", "progress": 1, ...}` ✅
- Upload > 100 MB → HTTP 413 "File too large" ✅
- Upload plain text jako .mp3 → HTTP 415 "Unsupported file type 'None'" ✅
- Upload PNG zmieniony na .mp3 → HTTP 415 "Unsupported file type 'image/png'" ✅
- GET status nieistniejącego joba → HTTP 404 ✅
- Worker log: `process_audio started — job_id=... file=...` ✅

**Status:** zakończone

**Następny krok:** Faza 2.2 — Demucs stem separation (pipeline/demucs.py)

## [2026-05-15] — Faza 2.2 — Demucs stem separation

**Faza/Krok:** Faza 2 / Krok 2.2

**Co zrobiono:**
- Stworzono `app/pipeline/demucs.py`:
  - `separate_stems(input_path, output_dir, job_id=None) → dict`
  - Model `htdemucs`, timeout 30 min (subprocess)
  - Mapowanie: htdemucs "other" → "melody"
  - Progress updates: 10% (start), 25% (done)
  - Weryfikacja plików output (exist + size > 0)
  - Lazy import `app.jobs` — brak circular import
- Naprawiono błąd Docker build: `audiocraft` zastąpiony przez `transformers accelerate encodec`
  (audiocraft 1.3.0 → spaCy/thinc niekompatybilne z Python 3.12)
- Dodano brakujące apt libs dla av: `libavdevice-dev libavfilter-dev libswscale-dev libswresample-dev`
  (ostatecznie usunięte wraz z audiocraft)
- Pełny obraz Docker zbudowany: `audio-app-worker:latest` (9.68GB — PyTorch CPU + cały stack)

**Zmienione pliki:**
- `app/pipeline/demucs.py` — nowy
- `Dockerfile` — audiocraft → transformers, usunięto zbędne av libs
- `KNOWN_ISSUES.md` — dwa nowe wpisy (permissions + audiocraft)

**Weryfikacja:**
- `separate_stems('/tmp/test_track.wav', '/tmp/demucs_out')` wewnątrz `audio-app-worker` ✅
- 4 stemy: vocals, drums, bass, melody (other.wav) — każdy 882,044 bytes ✅
- Czas: 6.5s dla 5-sekundowego tracku ✅
- Logger: `Demucs done in 6.5s — stems in /tmp/demucs_out/htdemucs/test_track` ✅

**Status:** zakończone

**Następny krok:** Faza 2.3 — Essentia analysis (pipeline/essentia_analysis.py)

## [2026-05-15] — Faza 2.3 — Essentia pełna analiza audio

**Faza/Krok:** Faza 2 / Krok 2.3

**Co zrobiono:**
- Stworzono `app/pipeline/essentia_analysis.py`:
  - `analyze_audio(file_path, job_id=None) → dict` (wszystkie pola z BUILD_PLAN)
  - BPM + beats: `RhythmExtractor2013(method="multifeature")`
  - Key + mode + camelot: `KeyExtractor` + mapowanie Camelot wheel (pełna tablica 24 kluczy)
  - Normalizacja enharmoniczna: Db→C#, Gb→F#, G#→Ab, A#→Bb (test assertion-safe)
  - Chord progression: pipeline HPCP → `ChordsDetection`, jeden akord co ~4s
  - Struktura: 3-częściowa heurystyka (intro/drop/outro), docelowo zastąpiona przez allin1fix (Faza 2.4)
  - Energy curve: RMS co 100ms, normalizacja 0-1
  - LUFS: `LoudnessEBUR128` (mono duplikowane do stereo), fallback RMS
  - Dynamic range: peak/RMS w dB
  - Spektrum: centroid (Hz), brightness (energia >1500Hz), bass_intensity (energia <250Hz)
  - Stereo width: `AudioLoader` → korelacja L/R → 0=mono, 1=max wide
  - Waveform RGB: 3 pasma (low/mid/high) co 10ms, normalizacja 0-1, dla Pixi.js
  - Progress: 25% (start) → 45% (done)

**Zmienione pliki:**
- `app/pipeline/essentia_analysis.py` — nowy

**Weryfikacja (test track: 12s, 128 BPM, ton A 440Hz):**
- `60 < result["bpm"] < 200` → bpm=128.02 ✅
- `result["key"] in VALID_KEYS` → key="Am" ✅
- `len(result["segments"]) > 0` → 3 segmenty [intro/drop/outro] ✅
- `len(result["waveform"]["low"]) > 0` → 1199 frames ✅
- Camelot: "8A" (A minor = poprawnie) ✅
- LUFS: -16.8 LUFS ✅
- Czas analizy: 0.3s na 12-sekundowy plik ✅

**Status:** zakończone

**Następny krok:** Faza 2.4 — allin1fix beat grid + structure detection (pipeline/allin1fix.py)

## [2026-05-15] — Faza 2.4 — allin1fix beat grid + structure detection

**Faza/Krok:** Faza 2 / Krok 2.4

**Co zrobiono:**
- Stworzono `app/pipeline/allin1fix.py`:
  - `analyze_beats(file_path, stems_dir=None, job_id=None) → dict`
  - Przyjmuje pre-separated stems z Demucs przez `create_stems_input_from_directory(stems_dir)`
  - Używa `device='cpu'`, `multiprocess=False`, `keep_byproducts=False`
  - Temp dirs dla `spec_dir` i `demix_dir` — bez śmiecenia w /app
  - `_compute_phrases()`: 4bar/8bar/16bar boundary times z downbeats
  - Progress: 45% (start) → 60% (done)
- Naprawiono natten CPU crash: `get_device_cc()` w `natten/utils/misc.py` nie sprawdzało `torch.cuda.is_available()` — crashowało na CPU-only PyTorchu
  - Fix: patch pliku podczas docker build (KROK 3c w Dockerfile)
- Dodano `KROK 3c` do Dockerfile: python3 -c "..." patch natten + weryfikacja `import allin1fix`

**Zwracane pola:**
- `beats`: lista timestampów wszystkich beatów
- `downbeats`: lista timestampów downbeatów (pierwsza jedynka każdego bara)
- `bpm_precise`: BPM z modelu (float, allin1fix zwraca int → cast)
- `beat_positions`: pozycja beatu w barze (1/2/3/4)
- `segments`: lista `{label, start, end}` — etykiety z HARMONIX_LABELS
- `phrases`: `{4bar, 8bar, 16bar}` — czasy granic fraz
- `time_signature`: "4/4" (model zakłada 4/4)

**Zmienione pliki:**
- `app/pipeline/allin1fix.py` — nowy
- `Dockerfile` — KROK 3c: natten CPU patch + import verification

**Weryfikacja (15s WAV, 128 BPM, stereo):**
- `len(result["beats"]) > 0` → 31 beatów ✅
- `len(result["downbeats"]) > 0` → 7 downbeatów ✅
- `len(result["downbeats"]) < len(result["beats"])` → 7 < 31 ✅
- `result["bpm_precise"] == 128.0` ✅
- stems_dir mode (z Demucs): ✅
- standalone mode (plik bez stemów): ✅
- brak śmiecenia w /app/demix: ✅
- Czas analizy: ~38s dla 15s tracku na CPU

**Status:** zakończone

**Następny krok:** Faza 2.5 — Auto Cue Points (pipeline/cue_points.py)

## [2026-05-15] — Faza 2.5 — Auto Cue Points

**Faza/Krok:** Faza 2 / Krok 2.5

**Co zrobiono:**
- Stworzono `app/pipeline/cue_points.py`:
  - `generate_cue_points(analysis, beats_data, vocal_stem_path=None) → list`
  - Cue pointy: `mix_in`, `mix_out`, `drop`, `breakdown`, `vocal_in`, `8bar_N`
  - `_snap()` — snap do nearest/after/before downbeat lub beat (bisect dla wydajności)
  - `_seg_end()` / `_seg_start()` — szuka segmentu w allin1fix (HARMONIX_LABELS) i Essentia jako fallback
  - `_detect_vocal_start()` — analiza energii RMS 50ms frames z vocals.wav (próg: 5% peak)
  - `_beat_number()` — 1-indexed pozycja beatu w tablicy beats
  - Sortowanie wynikowej listy po czasie
- Kolory cue pointów: mix_in=#00E676, mix_out=#F44336, drop=#FF6D00, breakdown=#2196F3, vocal_in=#9C27B0, 8bar=#FFEB3B

**Zmienione pliki:**
- `app/pipeline/cue_points.py` — nowy

**Weryfikacja (15s WAV, 128 BPM):**
- `any(c["id"] == "mix_in"  for c in cues)` ✅
- `any(c["id"] == "mix_out" for c in cues)` ✅
- Każdy cue w odległości < 0.01s od beatu ✅
- Cue pointy posortowane po czasie ✅
- drop/8bar_0 na pierwszym downbeacie (1.87s) ✅

**Status:** zakończone

**Następny krok:** Faza 2.6 — MusicGen: Generowanie Intro/Outro (pipeline/musicgen.py)
