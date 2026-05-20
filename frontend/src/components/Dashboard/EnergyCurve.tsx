// ─── Energy Curve — SVG filled area chart ─────────────────────────────────────
//
// Computed from waveform_data frames: weighted sum of low/mid/high bands.
// Shows section backgrounds for context, then a smoothed energy fill + stroke.

const VW = 600;   // viewBox width
const VH = 80;    // viewBox height
const PAD_Y = 6;  // vertical padding so the line doesn't clip at edges

interface Section {
  label: string;
  start: number;
  end: number;
}

const SECTION_COLORS: Record<string, string> = {
  intro:     '#3b82f6',
  verse:     '#22c55e',
  chorus:    '#a855f7',
  drop:      '#a855f7',
  breakdown: '#f97316',
  bridge:    '#14b8a6',
  build:     '#eab308',
  outro:     '#ef4444',
};

// ─── maths helpers ────────────────────────────────────────────────────────────

function downsample(arr: number[], target: number): number[] {
  if (arr.length <= target) return arr;
  const step = arr.length / target;
  return Array.from({ length: target }, (_, i) => arr[Math.round(i * step)]);
}

function smooth(arr: number[], win: number): number[] {
  return arr.map((_, i) => {
    const s = Math.max(0, i - win);
    const e = Math.min(arr.length, i + win + 1);
    return arr.slice(s, e).reduce((a, b) => a + b, 0) / (e - s);
  });
}

function toSvgY(energy: number, max: number): number {
  const norm = max > 0 ? energy / max : 0;
  return VH - PAD_Y - norm * (VH - PAD_Y * 2);
}

// ─── component ────────────────────────────────────────────────────────────────

interface EnergyCurveProps {
  waveformData: number[][] | null;
  duration: number;
  sections: Section[];
}

export function EnergyCurve({ waveformData, duration, sections }: EnergyCurveProps) {
  // Build energy array from waveform frames
  const raw = (waveformData ?? []).map(([l = 0, m = 0, h = 0]) => l * 0.5 + m * 0.35 + h * 0.15);
  const target = Math.min(raw.length, VW);
  const sampled = target > 0 ? smooth(downsample(raw, target), 6) : [];
  const max = sampled.length > 0 ? Math.max(...sampled) : 1;

  // SVG polyline points (as [x, y] pairs)
  const pts: [number, number][] = sampled.map((e, i) => [
    (i / Math.max(sampled.length - 1, 1)) * VW,
    toSvgY(e, max),
  ]);

  const pointsStr = pts.map(([x, y]) => `${x},${y}`).join(' ');

  // Fill path: go across the top as the energy curve, then back along the bottom
  const fillPath =
    pts.length > 0
      ? `M 0,${VH} L ${pointsStr} L ${VW},${VH} Z`
      : '';

  // Section background rects (time → x)
  const timeToX = (t: number) => (t / Math.max(duration, 1)) * VW;

  return (
    <svg
      viewBox={`0 0 ${VW} ${VH}`}
      preserveAspectRatio="none"
      className="h-20 w-full"
      aria-label="Energy curve"
    >
      <defs>
        <linearGradient id="energy-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#7c3aed" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#7c3aed" stopOpacity="0.05" />
        </linearGradient>
      </defs>

      {/* ── section backgrounds ── */}
      {sections.map((sec) => {
        const x1 = timeToX(sec.start);
        const x2 = timeToX(sec.end);
        const col = SECTION_COLORS[sec.label.toLowerCase()] ?? '#555566';
        return (
          <rect
            key={sec.label + sec.start}
            x={x1} y={0} width={x2 - x1} height={VH}
            fill={col}
            fillOpacity={0.1}
          />
        );
      })}

      {/* ── horizontal grid lines (25 / 50 / 75%) ── */}
      {[0.25, 0.5, 0.75].map((p) => {
        const y = toSvgY(max * (1 - p), max);
        return (
          <line
            key={p}
            x1={0} y1={y} x2={VW} y2={y}
            stroke="#ffffff" strokeOpacity="0.06" strokeWidth="0.5"
          />
        );
      })}

      {/* ── filled area ── */}
      {fillPath && (
        <path d={fillPath} fill="url(#energy-fill)" />
      )}

      {/* ── stroke line ── */}
      {pts.length > 1 && (
        <polyline
          points={pointsStr}
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {/* ── empty state ── */}
      {pts.length === 0 && (
        <text x={VW / 2} y={VH / 2} textAnchor="middle" dominantBaseline="middle" fontSize="10" fill="#4b5563">
          Brak danych waveform
        </text>
      )}
    </svg>
  );
}
