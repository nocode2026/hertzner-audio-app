import { useEffect, useRef, useState } from 'react';
import { CamelotWheel } from '../Dashboard/CamelotWheel';
import { useReprocess } from '../../hooks/useReprocess';
import { camelotLabel, CAMELOT_WHEEL } from '../../utils/camelot';
import type { AnalysisData, BeatData, HarmonyData, JobResult } from '../../types';

// ─── helpers ──────────────────────────────────────────────────────────────────

const NOTE_SEMI: Record<string, number> = {
  C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4,
  F: 5, 'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8, A: 9,
  'A#': 10, Bb: 10, B: 11,
};

function rootSemitone(keyRoot: string | undefined): number | null {
  return keyRoot !== undefined ? NOTE_SEMI[keyRoot] ?? null : null;
}

// ─── subcomponents ────────────────────────────────────────────────────────────

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[10px] font-semibold uppercase tracking-widest text-gray-500">
      {children}
    </label>
  );
}

function SafetyBadge({ warn, text }: { warn: boolean; text: string }) {
  if (!warn) return null;
  return (
    <span className="ml-2 rounded bg-amber-900/50 px-1.5 py-0.5 text-[10px] text-amber-400">
      ⚠ {text}
    </span>
  );
}

// ─── BPM slider ───────────────────────────────────────────────────────────────

function BpmSlider({
  originalBpm,
  value,
  onChange,
}: {
  originalBpm: number;
  value: number;
  onChange: (v: number) => void;
}) {
  const min     = +(originalBpm * 0.85).toFixed(2);
  const max     = +(originalBpm * 1.15).toFixed(2);
  const safeMin = +(originalBpm * 0.90).toFixed(2);
  const safeMax = +(originalBpm * 1.10).toFixed(2);
  const pct     = ((value - min) / (max - min)) * 100;
  const change  = ((value - originalBpm) / originalBpm) * 100;
  const unsafe  = Math.abs(change) > 10;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-lg font-semibold text-white">{value.toFixed(2)}</span>
        <span className="text-xs text-gray-400">BPM</span>
        <span className={`text-xs ${unsafe ? 'text-amber-400' : 'text-gray-500'}`}>
          {change >= 0 ? '+' : ''}{change.toFixed(1)}%
        </span>
        <SafetyBadge warn={unsafe} text="&gt;10% — mogą być artefakty" />
      </div>

      {/* track with safe-zone overlay */}
      <div className="relative h-2 rounded-full bg-gray-800">
        {/* safe zone bar */}
        <div
          className="absolute inset-y-0 rounded-full bg-green-900/40"
          style={{
            left:  `${((safeMin - min) / (max - min)) * 100}%`,
            right: `${((max - safeMax) / (max - min)) * 100}%`,
          }}
        />
        {/* fill to cursor */}
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-violet-600"
          style={{ width: `${pct}%` }}
        />
        {/* original marker */}
        <div
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-gray-400"
          style={{ left: `${((originalBpm - min) / (max - min)) * 100}%` }}
        />
      </div>

      <input
        type="range"
        min={min}
        max={max}
        step={0.1}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full cursor-pointer accent-violet-500"
        style={{ marginTop: '-28px', opacity: 0, position: 'relative', height: '28px' }}
      />

      <div className="flex justify-between text-[10px] text-gray-600">
        <span>{min.toFixed(1)}</span>
        <span>Oryginał: {originalBpm.toFixed(2)}</span>
        <span>{max.toFixed(1)}</span>
      </div>
    </div>
  );
}

// ─── numeric input ────────────────────────────────────────────────────────────

function NumInput({
  value,
  onChange,
  min = 0,
  max,
  step = 0.001,
  unit = 's',
}: {
  value: number;
  onChange: (v: number) => void;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}) {
  return (
    <div className="flex items-center gap-2">
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (!isNaN(v)) onChange(Math.max(min, max !== undefined ? Math.min(max, v) : v));
        }}
        className="w-28 rounded-lg bg-gray-800 px-3 py-1.5 font-mono text-sm text-white
                   focus:outline-none focus:ring-1 focus:ring-violet-500"
      />
      <span className="text-sm text-gray-500">{unit}</span>
    </div>
  );
}

// ─── main component ───────────────────────────────────────────────────────────

interface EditorPanelProps {
  jobId: string;
  analysis: AnalysisData | null;
  beats: BeatData | null;
  harmony: HarmonyData | null;
  selectedIntro: number;
  selectedOutro: number;
  onReprocessed: (result: JobResult) => void;
}

export function EditorPanel({
  jobId, analysis, beats, harmony,
  selectedIntro, selectedOutro,
  onReprocessed,
}: EditorPanelProps) {
  const originalBpm = beats?.bpm ?? analysis?.bpm ?? 120;
  const originalFdb = beats?.first_downbeat ?? 0;
  const origSemi    = rootSemitone(harmony?.key_root);
  const origCamelot = harmony?.camelot ?? null;

  // ── form state ──────────────────────────────────────────────────────────────
  const [trimStart,  setTrimStart]  = useState(0);
  const [firstBeat,  setFirstBeat]  = useState(originalFdb);
  const [keyShift,   setKeyShift]   = useState(0);
  const [targetCam,  setTargetCam]  = useState<string | null>(origCamelot);
  const [bpmTarget,  setBpmTarget]  = useState(originalBpm);

  // Keep defaults in sync if props arrive late (async)
  const syncRef = useRef(false);
  useEffect(() => {
    if (syncRef.current) return;
    if (originalFdb) { setFirstBeat(originalFdb); syncRef.current = true; }
  }, [originalFdb]);
  useEffect(() => {
    setBpmTarget(originalBpm);
  }, [originalBpm]);
  useEffect(() => {
    setTargetCam(origCamelot);
  }, [origCamelot]);

  // ── reprocess hook ──────────────────────────────────────────────────────────
  const { state, jobStatus, newResult, error, submit, reset } = useReprocess(jobId);

  // Bubble new result to parent
  useEffect(() => {
    if (state === 'done' && newResult) {
      onReprocessed(newResult);
    }
  }, [state, newResult, onReprocessed]);

  // ── derived display values ──────────────────────────────────────────────────
  const keyShiftUnsafe = Math.abs(keyShift) > 2;
  const bpmChanged     = Math.abs(bpmTarget - originalBpm) > 0.05;

  // Target camelot label for display (e.g. "7A — Ebm")
  const targetKeyLabel = (() => {
    if (keyShift === 0 || !targetCam) return null;
    const m = targetCam.match(/^(\d+)([AB])$/i);
    if (!m) return null;
    const pos  = parseInt(m[1]);
    const mode = m[2].toUpperCase() as 'A' | 'B';
    return `${targetCam} — ${camelotLabel(pos, mode)}`;
  })();

  function handleKeySelect(shift: number, targetPos: number, targetMode: 'A' | 'B') {
    setKeyShift(shift);
    setTargetCam(`${targetPos}${targetMode}`);
  }

  function handleReset() {
    setTrimStart(0);
    setFirstBeat(originalFdb);
    setKeyShift(0);
    setTargetCam(origCamelot);
    setBpmTarget(originalBpm);
    reset();
  }

  function handleSubmit() {
    submit({
      trim_start:     trimStart,
      first_beat:     firstBeat,
      key_shift:      keyShift,
      bpm_target:     bpmChanged ? bpmTarget : null,
      selected_intro: selectedIntro,
      selected_outro: selectedOutro,
    });
  }

  const busy = state === 'submitting' || state === 'processing';

  // ── render ──────────────────────────────────────────────────────────────────
  return (
    <div className="rounded-2xl bg-gray-900/80 p-5">
      <h2 className="mb-5 text-xs font-semibold uppercase tracking-widest text-gray-500">
        Korekty
      </h2>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[auto_1fr]">
        {/* ── left: Camelot wheel (key shift) ── */}
        <div className="flex flex-col items-center gap-3">
          <Label>Zmiana tonacji</Label>

          <CamelotWheel
            camelot={targetCam}
            currentSemitone={origSemi}
            onKeySelect={handleKeySelect}
          />

          {/* shift summary */}
          <div className="text-center text-sm">
            {keyShift === 0 ? (
              <span className="text-gray-500">Bez zmiany</span>
            ) : (
              <>
                <span className="text-gray-400">
                  {origCamelot} → {' '}
                  <span className="font-semibold text-white">{targetKeyLabel}</span>
                </span>
                <br />
                <span className={`text-xs ${keyShiftUnsafe ? 'text-amber-400' : 'text-violet-300'}`}>
                  {keyShift > 0 ? '+' : ''}{keyShift} semitonów
                </span>
                <SafetyBadge warn={keyShiftUnsafe} text=">2 semi — mogą być artefakty" />
              </>
            )}
          </div>

          {/* quick semitone buttons */}
          <div className="flex items-center gap-1">
            {[-2, -1, 0, +1, +2].map((n) => (
              <button
                key={n}
                className={`h-7 w-9 rounded text-xs transition-colors ${
                  keyShift === n
                    ? 'bg-violet-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
                onClick={() => {
                  setKeyShift(n);
                  if (n === 0) {
                    setTargetCam(origCamelot);
                  } else if (origSemi !== null) {
                    const targetSemi = ((origSemi + n) % 12 + 12) % 12;
                    const origMode   = origCamelot?.slice(-1) as 'A' | 'B' | undefined ?? 'A';
                    const entry      = CAMELOT_WHEEL.find((e) =>
                      origMode === 'A' ? e.aSemi === targetSemi : e.bSemi === targetSemi,
                    );
                    if (entry) setTargetCam(`${entry.pos}${origMode}`);
                  }
                }}
              >
                {n > 0 ? `+${n}` : n}
              </button>
            ))}
          </div>
        </div>

        {/* ── right: numeric controls ── */}
        <div className="space-y-6">
          {/* BPM */}
          <div className="space-y-2">
            <Label>Korekta BPM</Label>
            <BpmSlider
              originalBpm={originalBpm}
              value={bpmTarget}
              onChange={setBpmTarget}
            />
          </div>

          {/* Trim */}
          <div className="space-y-2">
            <Label>
              Ucięcie ciszy na początku
              <span className="ml-2 font-normal normal-case text-gray-600">
                (dodaj offset w sekundach)
              </span>
            </Label>
            <NumInput value={trimStart} onChange={setTrimStart} min={0} max={60} step={0.1} />
          </div>

          {/* First beat */}
          <div className="space-y-2">
            <Label>
              Korekta pierwszej jedynki
              <span className="ml-2 font-normal normal-case text-gray-600">
                oryginał: {originalFdb.toFixed(3)} s
              </span>
            </Label>
            <NumInput value={firstBeat} onChange={setFirstBeat} min={0} max={30} step={0.001} />
          </div>
        </div>
      </div>

      {/* ── summary row ── */}
      <div className="mt-5 rounded-lg bg-gray-950/60 px-4 py-2.5 font-mono text-xs text-gray-400">
        trim={trimStart.toFixed(1)}s &nbsp;·&nbsp;
        beat={firstBeat.toFixed(3)}s &nbsp;·&nbsp;
        shift={keyShift > 0 ? `+${keyShift}` : keyShift} &nbsp;·&nbsp;
        bpm={bpmChanged ? bpmTarget.toFixed(2) : `${originalBpm.toFixed(2)} (bez zmiany)`}
      </div>

      {/* ── progress when processing ── */}
      {busy && (
        <div className="mt-4 space-y-1.5">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-800">
            <div
              className="h-full rounded-full bg-violet-500 transition-[width] duration-500"
              style={{ width: `${jobStatus?.progress ?? 0}%` }}
            />
          </div>
          <p className="text-xs text-gray-400">
            {state === 'submitting' ? 'Wysyłanie korekty…' : (jobStatus?.current_step?.replace(/_/g, ' ') ?? 'Przetwarzanie…')}
            {jobStatus ? ` (${jobStatus.progress}%)` : ''}
          </p>
        </div>
      )}

      {/* ── error ── */}
      {state === 'failed' && error && (
        <div className="mt-4 rounded-lg border border-red-900 bg-red-950/60 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ── done ── */}
      {state === 'done' && (
        <div className="mt-4 rounded-lg border border-green-900 bg-green-950/50 px-4 py-3 text-sm text-green-300">
          Korekta zastosowana — wyniki zaktualizowane.
        </div>
      )}

      {/* ── action buttons ── */}
      <div className="mt-5 flex gap-3">
        <button
          className="rounded-lg bg-gray-800 px-5 py-2 text-sm text-gray-300 hover:bg-gray-700 disabled:opacity-40"
          onClick={handleReset}
          disabled={busy}
        >
          Reset
        </button>
        <button
          className="flex-1 rounded-lg bg-violet-600 py-2 text-sm font-semibold text-white
                     hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed"
          onClick={handleSubmit}
          disabled={busy || !jobId}
        >
          {busy ? (state === 'submitting' ? 'Wysyłanie…' : 'Przetwarzanie…') : 'Zastosuj korekty ▶'}
        </button>
      </div>
    </div>
  );
}
