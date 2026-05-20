interface ProgressBarProps {
  progress: number;
  currentStep: string | null;
}

const STEPS = [
  { label: 'Konwersja audio', from: 0, to: 10 },
  { label: 'Separacja stemów (Demucs)', from: 10, to: 25 },
  { label: 'Analiza struktury i harmonii', from: 25, to: 60 },
  { label: 'Generowanie cue pointów', from: 60, to: 72 },
  { label: 'Generowanie intro/outro (AI)', from: 72, to: 95 },
  { label: 'Przygotowanie eksportu', from: 95, to: 100 },
];

function currentLabel(progress: number, currentStep: string | null): string {
  if (currentStep) return currentStep.replace(/_/g, ' ');
  const step = [...STEPS].reverse().find((s) => progress >= s.from);
  return step?.label ?? 'Przetwarzanie...';
}

export function ProgressBar({ progress, currentStep }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, progress));
  const label = currentLabel(clamped, currentStep);

  return (
    <div className="w-full space-y-3">
      <div className="flex items-center justify-between text-sm">
        <span className="text-gray-300">{label}</span>
        <span className="tabular-nums text-gray-400">{clamped}%</span>
      </div>

      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-800">
        <div
          role="progressbar"
          aria-valuenow={clamped}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-full rounded-full bg-gradient-to-r from-violet-600 to-violet-400 transition-[width] duration-500"
          style={{ width: `${clamped}%` }}
        />
      </div>

      <div className="flex justify-between">
        {STEPS.map((step) => {
          const done = clamped >= step.to;
          const active = clamped >= step.from && clamped < step.to;
          return (
            <div key={step.label} className="flex flex-col items-center gap-1">
              <div
                className={[
                  'h-2 w-2 rounded-full transition-colors',
                  done
                    ? 'bg-violet-400'
                    : active
                    ? 'bg-violet-500 ring-2 ring-violet-500/40'
                    : 'bg-gray-700',
                ].join(' ')}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
