import { useEffect, useState } from 'react';
import { AnalysisDashboard } from './components/Dashboard';
import { EditorPanel } from './components/Editor';
import { UploadView } from './components/Upload/UploadView';
import { VariationsPlayer } from './components/Variations';
import { WaveformView } from './components/Waveform';
import { useAudioPlayer } from './hooks/useAudioPlayer';
import type { JobResult } from './types';

type AppState = 'idle' | 'done';

// ─── helpers ──────────────────────────────────────────────────────────────────

function fmt(s: number): string {
  if (!isFinite(s) || s < 0) return '0:00';
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

function trackDisplayName(original_name: string): string {
  if (!original_name) return 'Nieznany utwór';
  return original_name.replace(/\.[^.]+$/, '');
}

// ─── track player bar ─────────────────────────────────────────────────────────

interface TrackPlayerProps {
  trackName: string;
  isPlaying: boolean;
  currentTime: number;
  duration: number;
  onPlay: () => void;
  onPause: () => void;
  onSeek: (t: number) => void;
}

function TrackPlayer({ trackName, isPlaying, currentTime, duration, onPlay, onPause, onSeek }: TrackPlayerProps) {
  const progress = duration > 0 ? currentTime / duration : 0;

  const handleBarClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    onSeek(Math.max(0, Math.min(duration, ratio * duration)));
  };

  return (
    <div className="flex items-center gap-3 px-1 pt-2">
      {/* play / pause */}
      <button
        onClick={isPlaying ? onPause : onPlay}
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-600 text-white hover:bg-violet-500 active:scale-95"
        aria-label={isPlaying ? 'Pauza' : 'Odtwórz'}
      >
        {isPlaying ? (
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
            <rect x="3" y="2" width="4" height="12" rx="1" />
            <rect x="9" y="2" width="4" height="12" rx="1" />
          </svg>
        ) : (
          <svg viewBox="0 0 16 16" fill="currentColor" className="h-4 w-4">
            <path d="M4 2.5l10 5.5-10 5.5V2.5z" />
          </svg>
        )}
      </button>

      {/* track name */}
      <span className="min-w-0 flex-1 truncate text-xs text-gray-300">{trackName}</span>

      {/* time */}
      <span className="shrink-0 font-mono text-[11px] text-gray-500">
        {fmt(currentTime)} / {fmt(duration)}
      </span>

      {/* progress bar */}
      <div
        className="h-1.5 w-32 shrink-0 cursor-pointer rounded-full bg-gray-700"
        onClick={handleBarClick}
      >
        <div
          className="h-full rounded-full bg-violet-500 transition-[width] duration-100"
          style={{ width: `${progress * 100}%` }}
        />
      </div>
    </div>
  );
}

// ─── result view ──────────────────────────────────────────────────────────────

interface ResultViewProps {
  result:         JobResult;
  onReset:        () => void;
  onResultUpdate: (r: JobResult) => void;
}

function ResultView({ result, onReset, onResultUpdate }: ResultViewProps) {
  const { isPlaying, currentTime, duration, play, pause, seek, load } = useAudioPlayer();
  const dur   = result.analysis?.duration ?? 0;
  const jobId = result.job_id;

  // Load original track once when result arrives
  useEffect(() => {
    load(`/api/download/${jobId}/original`);
  }, [jobId, load]);

  // Variation selection — lifted here so both VariationsPlayer and EditorPanel share it
  const [selectedIntro, setSelectedIntro] = useState(0);
  const [selectedOutro, setSelectedOutro] = useState(0);

  const trackName = trackDisplayName(result.original_name ?? '');

  return (
    <div className="min-h-screen bg-gray-950 p-5 text-white">
      <div className="mx-auto max-w-6xl space-y-5">
        {/* header */}
        <header className="flex items-center justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-bold tracking-tight">DJ Intro/Outro Generator</h1>
            {trackName !== 'Nieznany utwór' && (
              <p className="mt-0.5 truncate text-sm text-gray-400">{trackName}</p>
            )}
          </div>
          <button
            className="ml-4 shrink-0 rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
            onClick={onReset}
          >
            ← Nowy utwór
          </button>
        </header>

        {/* waveform + player */}
        <section className="rounded-2xl bg-gray-900 p-3">
          <WaveformView
            waveformData={result.analysis?.waveform_data ?? null}
            duration={dur}
            beats={result.beats}
            analysis={result.analysis}
            cuePoints={result.cue_points}
            currentTime={currentTime}
            onSeek={seek}
            height={160}
          />
          <TrackPlayer
            trackName={trackName}
            isPlaying={isPlaying}
            currentTime={currentTime}
            duration={duration}
            onPlay={play}
            onPause={pause}
            onSeek={seek}
          />
        </section>

        {/* analysis dashboard */}
        <AnalysisDashboard
          analysis={result.analysis}
          harmony={result.harmony}
          beats={result.beats}
          cuePoints={result.cue_points}
          duration={dur}
          onSeek={seek}
        />

        {/* variations player */}
        <VariationsPlayer
          jobId={jobId}
          variations={result.variations}
          selectedIntro={selectedIntro}
          selectedOutro={selectedOutro}
          onSelectIntro={setSelectedIntro}
          onSelectOutro={setSelectedOutro}
        />

        {/* editor / corrections */}
        <EditorPanel
          jobId={jobId}
          analysis={result.analysis}
          beats={result.beats}
          harmony={result.harmony}
          selectedIntro={selectedIntro}
          selectedOutro={selectedOutro}
          onReprocessed={onResultUpdate}
        />
      </div>
    </div>
  );
}

// ─── app root ────────────────────────────────────────────────────────────────

export default function App() {
  const [state, setState]   = useState<AppState>('idle');
  const [result, setResult] = useState<JobResult | null>(null);

  const handleDone = (r: JobResult) => {
    setResult(r);
    setState('done');
  };

  if (state === 'done' && result) {
    return (
      <ResultView
        result={result}
        onReset={() => { setState('idle'); setResult(null); }}
        onResultUpdate={(r) => setResult(r)}
      />
    );
  }

  return <UploadView onDone={handleDone} />;
}
