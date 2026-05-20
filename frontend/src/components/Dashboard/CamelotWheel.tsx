// ─── Camelot Wheel — SVG, 240×240 viewBox ────────────────────────────────────
//
// Outer ring = B (major), inner ring = A (minor).
// Clicking a segment calls onKeySelect(semitoneShift, targetPos, targetMode).

import {
  CAMELOT_WHEEL,
  isCompatible,
  parseCamelot,
  semitoneShift,
} from '../../utils/camelot';

// ─── geometry helpers ─────────────────────────────────────────────────────────

const CX = 120, CY = 120;
const R_INNER_A = 53, R_OUTER_A = 77;
const R_INNER_B = 79, R_OUTER_B = 103;
const GAP_DEG = 1.5;

function d2r(deg: number) { return (deg * Math.PI) / 180; }

function ringPath(pos: number, r1: number, r2: number): string {
  const sa = d2r((pos - 1) * 30 - 90 + GAP_DEG);
  const ea = d2r(pos * 30 - 90 - GAP_DEG);
  const c  = [Math.cos(sa), Math.sin(sa), Math.cos(ea), Math.sin(ea)];
  return [
    `M ${CX + r1 * c[0]} ${CY + r1 * c[1]}`,
    `L ${CX + r2 * c[0]} ${CY + r2 * c[1]}`,
    `A ${r2} ${r2} 0 0 1 ${CX + r2 * c[2]} ${CY + r2 * c[3]}`,
    `L ${CX + r1 * c[2]} ${CY + r1 * c[3]}`,
    `A ${r1} ${r1} 0 0 0 ${CX + r1 * c[0]} ${CY + r1 * c[1]}`,
    'Z',
  ].join(' ');
}

function midPoint(pos: number, rMid: number): [number, number] {
  const a = d2r((pos - 0.5) * 30 - 90);
  return [CX + rMid * Math.cos(a), CY + rMid * Math.sin(a)];
}

function sectorHue(pos: number) { return (pos - 1) * 30; }

function ringFill(pos: number, state: 'active' | 'compatible' | 'default'): string {
  const h = sectorHue(pos);
  if (state === 'active')     return `hsl(${h},85%,52%)`;
  if (state === 'compatible') return `hsl(${h},60%,34%)`;
  return `hsl(${h},35%,20%)`;
}

// ─── component ────────────────────────────────────────────────────────────────

export interface CamelotWheelProps {
  camelot: string | null;           // e.g. "8A" — which segment is highlighted
  currentSemitone: number | null;   // root of the *original* key for shift calculation
  /**
   * Called when user clicks a different segment.
   * shift     = semitones from original (shortest path, –6..+6)
   * targetPos = Camelot position 1-12
   * targetMode = 'A' (minor) or 'B' (major)
   */
  onKeySelect?: (shift: number, targetPos: number, targetMode: 'A' | 'B') => void;
}

export function CamelotWheel({ camelot, currentSemitone, onKeySelect }: CamelotWheelProps) {
  const active = camelot ? parseCamelot(camelot) : null;

  function handleClick(pos: number, mode: 'A' | 'B') {
    if (!onKeySelect || currentSemitone === null) return;
    const entry = CAMELOT_WHEEL.find((e) => e.pos === pos)!;
    const targetSemi = mode === 'A' ? entry.aSemi : entry.bSemi;
    onKeySelect(semitoneShift(currentSemitone, targetSemi), pos, mode);
  }

  return (
    <svg viewBox="0 0 240 240" width="200" height="200" aria-label="Camelot wheel">
      <circle cx={CX} cy={CY} r={107} fill="#0d0d14" />

      {CAMELOT_WHEEL.map((entry) => {
        const aState = active
          ? active.pos === entry.pos && active.mode === 'A' ? 'active'
          : isCompatible(active, entry.pos, 'A') ? 'compatible'
          : 'default'
          : 'default';
        const bState = active
          ? active.pos === entry.pos && active.mode === 'B' ? 'active'
          : isCompatible(active, entry.pos, 'B') ? 'compatible'
          : 'default'
          : 'default';

        const [axc, ayc] = midPoint(entry.pos, (R_INNER_A + R_OUTER_A) / 2);
        const [bxc, byc] = midPoint(entry.pos, (R_INNER_B + R_OUTER_B) / 2);

        return (
          <g key={entry.pos}>
            {/* inner ring — A / minor */}
            <path
              d={ringPath(entry.pos, R_INNER_A, R_OUTER_A)}
              fill={ringFill(entry.pos, aState)}
              className={onKeySelect ? 'cursor-pointer' : ''}
              onClick={() => handleClick(entry.pos, 'A')}
            >
              <title>{entry.pos}A — {entry.A}</title>
            </path>
            <text
              x={axc} y={ayc}
              textAnchor="middle" dominantBaseline="middle"
              fontSize="7"
              fontWeight={aState === 'active' ? 'bold' : 'normal'}
              fill={aState === 'default' ? '#9ca3af' : '#ffffff'}
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {entry.A}
            </text>

            {/* outer ring — B / major */}
            <path
              d={ringPath(entry.pos, R_INNER_B, R_OUTER_B)}
              fill={ringFill(entry.pos, bState)}
              className={onKeySelect ? 'cursor-pointer' : ''}
              onClick={() => handleClick(entry.pos, 'B')}
            >
              <title>{entry.pos}B — {entry.B}</title>
            </path>
            <text
              x={bxc} y={byc}
              textAnchor="middle" dominantBaseline="middle"
              fontSize="8"
              fontWeight={bState === 'active' ? 'bold' : 'normal'}
              fill={bState === 'default' ? '#9ca3af' : '#ffffff'}
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {entry.B}
            </text>
          </g>
        );
      })}

      {/* centre: position + key name */}
      <circle cx={CX} cy={CY} r={50} fill="#111120" />
      {active ? (
        <>
          <text
            x={CX} y={CY - 10}
            textAnchor="middle" dominantBaseline="middle"
            fontSize="22" fontWeight="bold"
            fill={`hsl(${sectorHue(active.pos)},80%,62%)`}
          >
            {active.pos}{active.mode}
          </text>
          <text
            x={CX} y={CY + 14}
            textAnchor="middle" dominantBaseline="middle"
            fontSize="11" fill="#d1d5db"
          >
            {CAMELOT_WHEEL.find((e) => e.pos === active.pos)?.[active.mode]}
          </text>
        </>
      ) : (
        <text x={CX} y={CY} textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="#4b5563">
          —
        </text>
      )}
    </svg>
  );
}
