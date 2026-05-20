// ─── Structure Timeline — horizontal proportional section bar ─────────────────

interface Section {
  label: string;
  start: number;
  end: number;
}

const SECTION_COLORS: Record<string, string> = {
  intro:     'bg-blue-600/70',
  verse:     'bg-green-600/70',
  chorus:    'bg-purple-600/70',
  drop:      'bg-purple-600/70',
  breakdown: 'bg-orange-500/70',
  bridge:    'bg-teal-500/70',
  build:     'bg-yellow-500/70',
  outro:     'bg-red-600/70',
};

const LABEL_COLORS: Record<string, string> = {
  intro:     'text-blue-300',
  verse:     'text-green-300',
  chorus:    'text-purple-300',
  drop:      'text-purple-300',
  breakdown: 'text-orange-300',
  bridge:    'text-teal-300',
  build:     'text-yellow-300',
  outro:     'text-red-300',
};

function fmt(s: number): string {
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

interface StructureTimelineProps {
  sections: Section[];
  duration: number;
  onSeek?: (time: number) => void;
}

export function StructureTimeline({ sections, duration, onSeek }: StructureTimelineProps) {
  if (sections.length === 0 || duration <= 0) {
    return (
      <div className="flex h-10 items-center rounded-lg bg-gray-800/50 px-4">
        <span className="text-xs text-gray-500">Brak danych struktury</span>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* proportional bar */}
      <div className="flex h-8 w-full overflow-hidden rounded-lg">
        {sections.map((sec) => {
          const pct = ((sec.end - sec.start) / duration) * 100;
          const key = sec.label.toLowerCase();
          const bg  = SECTION_COLORS[key] ?? 'bg-gray-600/70';
          return (
            <div
              key={sec.label + sec.start}
              className={`${bg} flex cursor-pointer items-center justify-center overflow-hidden transition-opacity hover:opacity-80`}
              style={{ width: `${pct}%` }}
              title={`${sec.label}: ${fmt(sec.start)} – ${fmt(sec.end)}`}
              onClick={() => onSeek?.(sec.start)}
            >
              {/* only show label if wide enough (> 5%) */}
              {pct > 5 && (
                <span className="truncate px-1 text-[9px] font-semibold uppercase tracking-wide text-white/90">
                  {sec.label}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* section legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {sections.map((sec) => {
          const key   = sec.label.toLowerCase();
          const color = LABEL_COLORS[key] ?? 'text-gray-400';
          return (
            <button
              key={sec.label + sec.start}
              className={`text-xs ${color} hover:underline`}
              onClick={() => onSeek?.(sec.start)}
            >
              {sec.label}{' '}
              <span className="font-mono text-gray-500">{fmt(sec.start)}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
