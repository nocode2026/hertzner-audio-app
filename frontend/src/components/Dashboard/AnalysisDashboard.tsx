import type { AnalysisData, BeatData, CuePoint, HarmonyData } from '../../types';
import { CamelotWheel } from './CamelotWheel';
import { EnergyCurve } from './EnergyCurve';
import { StructureTimeline } from './StructureTimeline';

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmt(s: number): string {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function parseSections(
  structure: Record<string, unknown> | null | undefined,
): { label: string; start: number; end: number }[] {
  const segs = (structure as { segments?: unknown } | null)?.segments;
  if (!Array.isArray(segs)) return [];
  return segs
    .filter(
      (s): s is { label: string; start: number; end: number } =>
        !!s &&
        typeof (s as { label?: unknown }).label === 'string' &&
        typeof (s as { start?: unknown }).start === 'number' &&
        typeof (s as { end?: unknown }).end === 'number',
    )
    .map((s) => ({ label: s.label, start: s.start, end: s.end }));
}

// ─── stat card ────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="rounded-xl bg-gray-900/80 px-4 py-3">
      <dt className="text-[10px] uppercase tracking-widest text-gray-500">{label}</dt>
      <dd className="mt-1 font-mono text-xl font-semibold text-white">{value}</dd>
      {sub && <dd className="mt-0.5 text-xs text-gray-500">{sub}</dd>}
    </div>
  );
}

// ─── chord progression strip ──────────────────────────────────────────────────

function ChordStrip({ chords }: { chords: string[] }) {
  if (chords.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <div className="flex gap-1.5 pb-1">
        {chords.map((ch, i) => (
          <span
            key={i}
            className="shrink-0 rounded bg-gray-800 px-2.5 py-1 font-mono text-xs text-violet-300"
          >
            {ch}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─── cue points table ─────────────────────────────────────────────────────────

const CUE_COLORS: Record<string, string> = {
  mix_in:    'bg-green-500',
  mix_out:   'bg-orange-500',
  drop:      'bg-yellow-400',
  vocal_in:  'bg-cyan-400',
  breakdown: 'bg-red-500',
};

function CueTable({
  cuePoints,
  onSeek,
}: {
  cuePoints: CuePoint[];
  onSeek: (time: number) => void;
}) {
  if (cuePoints.length === 0) return null;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-[10px] uppercase tracking-wider text-gray-500">
          <th className="pb-2 pr-3 font-normal">Typ</th>
          <th className="pb-2 pr-3 font-normal">Czas</th>
          <th className="pb-2 font-normal">Beat</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-800/60">
        {cuePoints.map((cp) => (
          <tr
            key={cp.label + cp.time}
            className="cursor-pointer hover:bg-gray-800/50"
            onClick={() => onSeek(cp.time)}
          >
            <td className="py-1.5 pr-3">
              <span className="flex items-center gap-2 text-gray-200">
                <span
                  className={`inline-block h-2 w-2 rounded-full ${CUE_COLORS[cp.label] ?? 'bg-violet-500'}`}
                />
                {cp.label.replace(/_/g, ' ')}
              </span>
            </td>
            <td className="py-1.5 pr-3 font-mono text-gray-300">{cp.time.toFixed(3)}</td>
            <td className="py-1.5 font-mono text-gray-500">{cp.beat ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ─── main dashboard ───────────────────────────────────────────────────────────

interface AnalysisDashboardProps {
  analysis: AnalysisData | null;
  harmony: HarmonyData | null;
  beats: BeatData | null;
  cuePoints: CuePoint[] | null;
  duration: number;
  onSeek: (time: number) => void;
  /** Optional: receive key shift when user clicks Camelot wheel */
  onKeyShift?: (shift: number, targetPos: number, targetMode: 'A' | 'B') => void;
}

export function AnalysisDashboard({
  analysis,
  harmony,
  beats,
  cuePoints,
  duration,
  onSeek,
  onKeyShift,
}: AnalysisDashboardProps) {
  const sections = parseSections(analysis?.structure);
  const bpm      = beats?.bpm ?? analysis?.bpm;
  const bpmConf  = analysis?.bpm_confidence;
  const key      = harmony?.key ?? analysis?.key;
  const mode     = harmony?.mode ?? analysis?.mode;
  const camelot  = harmony?.camelot ?? null;
  const loudness = analysis?.loudness_integrated;
  const dur      = duration || analysis?.duration || 0;

  // Root semitone for key-shift calculation
  const rootSemitone: number | null = (() => {
    if (!harmony?.key_root) return null;
    const NOTE_MAP: Record<string, number> = {
      C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4,
      F: 5, 'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8, A: 9,
      'A#': 10, Bb: 10, B: 11,
    };
    return NOTE_MAP[harmony.key_root] ?? null;
  })();

  return (
    <div className="space-y-5">
      {/* ── stat cards row ── */}
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-5">
        <StatCard
          label="BPM"
          value={bpm ? bpm.toFixed(2) : '—'}
          sub={bpmConf !== undefined ? `${Math.round(bpmConf * 100)}% conf.` : undefined}
        />
        <StatCard
          label="Tonacja"
          value={key ? `${key} ${mode ?? ''}`.trim() : '—'}
          sub={camelot ?? undefined}
        />
        <StatCard
          label="Loudness"
          value={loudness !== undefined ? `${loudness.toFixed(1)} LUFS` : '—'}
        />
        <StatCard
          label="Czas trwania"
          value={dur ? fmt(dur) : '—'}
        />
        {beats?.first_downbeat !== undefined && (
          <StatCard
            label="Pierwsza jedynka"
            value={`${beats.first_downbeat.toFixed(3)} s`}
          />
        )}
      </dl>

      {/* ── Camelot wheel + Energy curve ── */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[auto_1fr]">
        {/* Camelot wheel */}
        <div className="flex flex-col items-center rounded-2xl bg-gray-900/80 p-5">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-500">
            Camelot Wheel
          </h3>
          <CamelotWheel
            camelot={camelot}
            currentSemitone={rootSemitone}
            onKeySelect={onKeyShift}
          />
          {harmony?.chord_progression && harmony.chord_progression.length > 0 && (
            <div className="mt-4 w-full max-w-[220px]">
              <p className="mb-2 text-[10px] uppercase tracking-wider text-gray-500">
                Progresja akordów
              </p>
              <ChordStrip chords={harmony.chord_progression.slice(0, 16)} />
            </div>
          )}
        </div>

        {/* Energy curve */}
        <div className="flex flex-col rounded-2xl bg-gray-900/80 p-5">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-500">
            Krzywa energii
          </h3>
          <div className="rounded-lg bg-gray-950/60 p-2">
            <EnergyCurve
              waveformData={analysis?.waveform_data ?? null}
              duration={dur}
              sections={sections}
            />
          </div>

          {/* Structure timeline below the curve, inside same card */}
          {sections.length > 0 && (
            <div className="mt-4">
              <p className="mb-2 text-[10px] uppercase tracking-wider text-gray-500">
                Struktura
              </p>
              <StructureTimeline
                sections={sections}
                duration={dur}
                onSeek={onSeek}
              />
            </div>
          )}
        </div>
      </div>

      {/* ── Cue points table ── */}
      {cuePoints && cuePoints.length > 0 && (
        <div className="rounded-2xl bg-gray-900/80 p-5">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-widest text-gray-500">
            Cue Points
          </h3>
          <CueTable cuePoints={cuePoints} onSeek={onSeek} />
        </div>
      )}
    </div>
  );
}
