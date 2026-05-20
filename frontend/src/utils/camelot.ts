// Single source of truth for Camelot wheel data and key-shift maths.

export interface WheelEntry {
  pos: number;
  A: string;     // minor key label, e.g. "Am"
  B: string;     // major key label, e.g. "C"
  aSemi: number; // root semitone (0=C) for minor
  bSemi: number; // root semitone for major
}

export const CAMELOT_WHEEL: WheelEntry[] = [
  { pos: 1,  A: 'Am',  B: 'C',  aSemi: 9,  bSemi: 0  },
  { pos: 2,  A: 'Em',  B: 'G',  aSemi: 4,  bSemi: 7  },
  { pos: 3,  A: 'Bm',  B: 'D',  aSemi: 11, bSemi: 2  },
  { pos: 4,  A: 'F#m', B: 'A',  aSemi: 6,  bSemi: 9  },
  { pos: 5,  A: 'C#m', B: 'E',  aSemi: 1,  bSemi: 4  },
  { pos: 6,  A: 'G#m', B: 'B',  aSemi: 8,  bSemi: 11 },
  { pos: 7,  A: 'Ebm', B: 'F#', aSemi: 3,  bSemi: 6  },
  { pos: 8,  A: 'Bbm', B: 'Db', aSemi: 10, bSemi: 1  },
  { pos: 9,  A: 'Fm',  B: 'Ab', aSemi: 5,  bSemi: 8  },
  { pos: 10, A: 'Cm',  B: 'Eb', aSemi: 0,  bSemi: 3  },
  { pos: 11, A: 'Gm',  B: 'Bb', aSemi: 7,  bSemi: 10 },
  { pos: 12, A: 'Dm',  B: 'F',  aSemi: 2,  bSemi: 5  },
];

/**
 * Shortest semitone shift from `from` to `to` (result in [-6, +6]).
 */
export function semitoneShift(from: number, to: number): number {
  let s = (to - from + 12) % 12;
  return s > 6 ? s - 12 : s;
}

/**
 * Parse a Camelot string like "8A" → { pos: 8, mode: 'A' }
 */
export function parseCamelot(cam: string): { pos: number; mode: 'A' | 'B' } | null {
  const m = cam.match(/^(\d+)([AB])$/i);
  if (!m) return null;
  return { pos: parseInt(m[1]), mode: m[2].toUpperCase() as 'A' | 'B' };
}

/**
 * Two Camelot positions are compatible if they share the same number (different mode)
 * or are adjacent numbers in the same mode.
 */
export function isCompatible(
  cur: { pos: number; mode: 'A' | 'B' },
  pos: number,
  mode: 'A' | 'B',
): boolean {
  const adj = Math.abs(cur.pos - pos) === 1 || Math.abs(cur.pos - pos) === 11;
  return (cur.pos === pos && cur.mode !== mode) || (adj && cur.mode === mode);
}

/**
 * Look up the key label for a given Camelot position + mode, e.g. (8, 'A') → "Bbm".
 */
export function camelotLabel(pos: number, mode: 'A' | 'B'): string {
  const entry = CAMELOT_WHEEL.find((e) => e.pos === pos);
  if (!entry) return '?';
  return entry[mode];
}
