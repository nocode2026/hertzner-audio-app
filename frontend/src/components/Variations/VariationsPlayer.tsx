import { useState } from 'react';
import type { VariationsData } from '../../types';
import { VariantCard } from './VariantCard';

// Build the audio URL from jobId + type + index.
// The backend serves: GET /api/download/{job_id}/intro_0 (etc.)
function audioUrl(jobId: string, type: 'intro' | 'outro', index: number): string {
  return `/api/download/${jobId}/${type}_${index}`;
}

interface VariationsPlayerProps {
  jobId:          string;
  variations:     VariationsData | null;
  selectedIntro:  number;
  selectedOutro:  number;
  onSelectIntro:  (i: number) => void;
  onSelectOutro:  (i: number) => void;
}

type PlayingKey = `intro_${number}` | `outro_${number}` | null;

export function VariationsPlayer({
  jobId,
  variations,
  selectedIntro,
  selectedOutro,
  onSelectIntro,
  onSelectOutro,
}: VariationsPlayerProps) {
  const [playingKey, setPlayingKey] = useState<PlayingKey>(null);

  if (!variations) {
    return (
      <div className="flex h-24 items-center justify-center rounded-2xl bg-gray-900/60">
        <p className="text-sm text-gray-500">Brak wygenerowanych wariantów</p>
      </div>
    );
  }

  const { intros, outros } = variations;

  function renderSection(
    type: 'intro' | 'outro',
    paths: (string | null)[],
    selected: number,
    onSelect: (i: number) => void,
  ) {
    const label = type === 'intro' ? 'Intro' : 'Outro';
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400">
            {label}
          </h3>
          <span className="text-[10px] text-gray-600">
            — wybrany: Wariant {selected + 1}
          </span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {([0, 1, 2] as const).map((i) => {
            const key: PlayingKey = `${type}_${i}`;
            return (
              <VariantCard
                key={key}
                type={type}
                index={i}
                available={paths[i] !== null && paths[i] !== undefined}
                url={audioUrl(jobId, type, i)}
                selected={selected === i}
                onSelect={() => onSelect(i)}
                onPlay={() => setPlayingKey(key)}
                shouldStop={playingKey !== null && playingKey !== key}
              />
            );
          })}
        </div>
      </div>
    );
  }

  const hasAnyIntro = intros.some(Boolean);
  const hasAnyOutro = outros.some(Boolean);

  return (
    <div className="rounded-2xl bg-gray-900/80 p-5">
      <h2 className="mb-5 text-xs font-semibold uppercase tracking-widest text-gray-500">
        Warianty intro / outro
      </h2>

      <div className="space-y-6">
        {hasAnyIntro
          ? renderSection('intro', intros, selectedIntro, onSelectIntro)
          : <p className="text-sm text-gray-500">Brak wygenerowanych intro</p>}

        {hasAnyOutro
          ? renderSection('outro', outros, selectedOutro, onSelectOutro)
          : <p className="text-sm text-gray-500">Brak wygenerowanych outro</p>}
      </div>
    </div>
  );
}
