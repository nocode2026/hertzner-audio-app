import { useEffect, useRef, useState } from 'react';
import type { AnalysisData, BeatData, CuePoint } from '../../types';
import type {
  WaveformCuePoint,
  WaveformRenderer,
  WaveformSection,
} from './WaveformRenderer';

interface WaveformViewProps {
  waveformData: number[][] | null;
  duration: number;
  beats: BeatData | null;
  analysis: AnalysisData | null;
  cuePoints: CuePoint[] | null;
  currentTime: number;
  onSeek: (time: number) => void;
  height?: number;
}

// Parse sections from the opaque analysis.structure field
function parseSections(structure: Record<string, unknown> | null | undefined): WaveformSection[] {
  if (!structure) return [];
  const segs = (structure as { segments?: unknown }).segments;
  if (!Array.isArray(segs)) return [];
  const out: WaveformSection[] = [];
  for (const s of segs) {
    if (
      s &&
      typeof (s as { label?: unknown }).label === 'string' &&
      typeof (s as { start?: unknown }).start === 'number' &&
      typeof (s as { end?: unknown }).end === 'number'
    ) {
      out.push({ label: s.label, start: s.start, end: s.end });
    }
  }
  return out;
}

export function WaveformView({
  waveformData,
  duration,
  beats,
  analysis,
  cuePoints,
  currentTime,
  onSeek,
  height = 160,
}: WaveformViewProps) {
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef  = useRef<WaveformRenderer | null>(null);
  const onSeekRef    = useRef(onSeek);
  const [ready, setReady] = useState(false);

  // Keep seek ref current so the renderer callback is never stale
  useEffect(() => { onSeekRef.current = onSeek; }, [onSeek]);

  // ── Pixi.js lifecycle (dynamic import keeps pixi.js in its own chunk) ────────
  useEffect(() => {
    if (!canvasRef.current) return;
    let destroyed = false;

    import('./WaveformRenderer').then(({ WaveformRenderer }) => {
      if (destroyed) return;
      const renderer = new WaveformRenderer();

      renderer.init(canvasRef.current!, (t) => onSeekRef.current(t)).then(() => {
        if (destroyed) { renderer.destroy(); return; }
        rendererRef.current = renderer;
        setReady(true);
      });
    });

    return () => {
      destroyed = true;
      rendererRef.current?.destroy();
      rendererRef.current = null;
      setReady(false);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Resize observer ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;
    const obs = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? 0;
      if (w > 0) rendererRef.current?.resize(w, height);
    });
    obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, [height]);

  // ── Draw waveform when data or ready state changes ─────────────────────────
  useEffect(() => {
    if (!ready || !rendererRef.current || duration <= 0) return;

    const sections: WaveformSection[] = parseSections(analysis?.structure);
    const cues: WaveformCuePoint[] = (cuePoints ?? []).map((c) => ({
      label: c.label,
      time:  c.time,
    }));

    rendererRef.current.setData({
      frames:    waveformData,
      duration,
      beats:     beats?.beats     ?? [],
      downbeats: beats?.downbeats ?? [],
      phrases:   beats?.phrases   ?? [],
      sections,
      cuePoints: cues,
    });
  }, [ready, waveformData, duration, beats, analysis, cuePoints]);

  // ── Cursor updates (no full redraw) ────────────────────────────────────────
  useEffect(() => {
    if (!ready) return;
    rendererRef.current?.updateCursor(currentTime);
  }, [ready, currentTime]);

  return (
    <div
      ref={containerRef}
      className="relative w-full overflow-hidden rounded-xl bg-[#0d0d14]"
      style={{ height }}
    >
      <canvas ref={canvasRef} style={{ display: 'block' }} />

      {/* Hint overlay — bottom-right corner */}
      <div className="pointer-events-none absolute bottom-2 right-3 select-none text-[10px] text-gray-600">
        scroll&nbsp;= zoom · drag&nbsp;= pan · click&nbsp;= seek
      </div>

      {/* Loading state */}
      {!ready && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-xs text-gray-500">Initialising waveform…</span>
        </div>
      )}
    </div>
  );
}
