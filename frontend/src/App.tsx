import { useState } from 'react';
import { AnalysisDashboard } from './components/Dashboard';
import { EditorPanel } from './components/Editor';
import { UploadView } from './components/Upload/UploadView';
import { VariationsPlayer } from './components/Variations';
import { WaveformView } from './components/Waveform';
import { useAudioPlayer } from './hooks/useAudioPlayer';
import type { JobResult } from './types';

type AppState = 'idle' | 'done';

// ─── result view ──────────────────────────────────────────────────────────────

interface ResultViewProps {
  result:         JobResult;
  onReset:        () => void;
  onResultUpdate: (r: JobResult) => void;
}

function ResultView({ result, onReset, onResultUpdate }: ResultViewProps) {
  const { currentTime, seek } = useAudioPlayer();
  const dur   = result.analysis?.duration ?? 0;
  const jobId = result.job_id;

  // Variation selection — lifted here so both VariationsPlayer and EditorPanel share it
  const [selectedIntro, setSelectedIntro] = useState(0);
  const [selectedOutro, setSelectedOutro] = useState(0);

  return (
    <div className="min-h-screen bg-gray-950 p-5 text-white">
      <div className="mx-auto max-w-6xl space-y-5">
        {/* header */}
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold tracking-tight">DJ Intro/Outro Generator</h1>
          <button
            className="rounded-lg bg-gray-800 px-4 py-2 text-sm text-gray-300 hover:bg-gray-700"
            onClick={onReset}
          >
            ← Nowy utwór
          </button>
        </header>

        {/* waveform */}
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
