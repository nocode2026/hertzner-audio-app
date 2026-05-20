import { useEffect, useRef, useState } from 'react';

// ─── mini waveform (peak-extracted via Web Audio API) ─────────────────────────

function MiniWaveform({
  peaks,
  progress,
  available,
}: {
  peaks: number[] | null;
  progress: number;  // 0–1
  available: boolean;
}) {
  const W = 100, H = 40;
  const cy = H / 2;

  return (
    <div className="relative h-10 w-full overflow-hidden rounded">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="absolute inset-0 h-full w-full"
        preserveAspectRatio="none"
      >
        {peaks
          ? peaks.map((p, i) => {
              const bh = Math.max(1, p * cy * 1.9);
              return (
                <rect
                  key={i}
                  x={(i / peaks.length) * W}
                  y={cy - bh / 2}
                  width={W / peaks.length - 0.3}
                  height={bh}
                  fill="#8b5cf6"
                  opacity={0.65}
                />
              );
            })
          : // placeholder bars when not loaded yet
            Array.from({ length: 40 }, (_, i) => (
              <rect
                key={i}
                x={(i / 40) * W}
                y={cy - 3}
                width={W / 40 - 0.3}
                height={available ? 6 : 2}
                fill={available ? '#4b5563' : '#1f2937'}
                opacity={0.6}
              />
            ))}
      </svg>

      {/* playback progress overlay */}
      <div
        className="pointer-events-none absolute inset-y-0 left-0 bg-violet-400/25 transition-[width]"
        style={{ width: `${progress * 100}%` }}
      />
    </div>
  );
}

// ─── time formatter ───────────────────────────────────────────────────────────

function fmtTime(s: number): string {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
}

// ─── card ─────────────────────────────────────────────────────────────────────

interface VariantCardProps {
  type:      'intro' | 'outro';
  index:     0 | 1 | 2;
  available: boolean;
  url:       string;
  selected:  boolean;
  /** Call when this card starts playing — parent uses it to stop others */
  onPlay:    () => void;
  onSelect:  () => void;
  /** Parent sets this to true when another card starts playing */
  shouldStop: boolean;
}

export function VariantCard({
  type,
  index,
  available,
  url,
  selected,
  onPlay,
  onSelect,
  shouldStop,
}: VariantCardProps) {
  const audioRef    = useRef<HTMLAudioElement | null>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [curTime,   setCurTime]   = useState(0);
  const [duration,  setDuration]  = useState<number | null>(null);
  const [peaks,     setPeaks]     = useState<number[] | null>(null);

  // ── Audio element setup ───────────────────────────────────────────────────
  useEffect(() => {
    if (!available) return;
    const audio = new Audio(url);
    audio.preload = 'metadata';
    audioRef.current = audio;

    const onTime  = () => setCurTime(audio.currentTime);
    const onMeta  = () => setDuration(audio.duration);
    const onEnded = () => { setIsPlaying(false); setCurTime(0); };

    audio.addEventListener('timeupdate',     onTime);
    audio.addEventListener('durationchange', onMeta);
    audio.addEventListener('ended',          onEnded);

    return () => {
      audio.pause();
      audio.removeEventListener('timeupdate',     onTime);
      audio.removeEventListener('durationchange', onMeta);
      audio.removeEventListener('ended',          onEnded);
    };
  }, [url, available]);

  // ── Peak extraction for mini waveform ────────────────────────────────────
  useEffect(() => {
    if (!available) return;
    let cancelled = false;

    fetch(url)
      .then((r) => r.arrayBuffer())
      .then((buf) => {
        const ctx = new AudioContext();
        return ctx.decodeAudioData(buf).then((decoded) => {
          ctx.close();
          return decoded;
        });
      })
      .then((decoded) => {
        if (cancelled) return;
        const ch   = decoded.getChannelData(0);
        const N    = 80;
        const step = Math.floor(ch.length / N);
        const ps: number[] = [];
        for (let i = 0; i < N; i++) {
          const start = i * step;
          let max = 0;
          for (let j = start; j < Math.min(start + step, ch.length); j++) {
            const a = Math.abs(ch[j]);
            if (a > max) max = a;
          }
          ps.push(max);
        }
        setPeaks(ps);
      })
      .catch(() => { /* silently degrade — card still plays */ });

    return () => { cancelled = true; };
  }, [url, available]);

  // ── Stop when parent signals ──────────────────────────────────────────────
  useEffect(() => {
    if (!shouldStop) return;
    const a = audioRef.current;
    if (a) { a.pause(); a.currentTime = 0; }
    setIsPlaying(false);
    setCurTime(0);
  }, [shouldStop]);

  function togglePlay() {
    const a = audioRef.current;
    if (!a) return;
    if (isPlaying) {
      a.pause();
      setIsPlaying(false);
    } else {
      onPlay();          // stop siblings
      a.play().catch(() => {});
      setIsPlaying(true);
    }
  }

  const progress = duration ? curTime / duration : 0;
  const label    = `Wariant ${index + 1}`;

  return (
    <div
      className={[
        'flex flex-col gap-3 rounded-xl border p-3 transition-colors',
        selected
          ? 'border-violet-500 bg-violet-950/30'
          : 'border-gray-700 bg-gray-900/60',
        !available && 'opacity-50',
      ].join(' ')}
    >
      {/* header row */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-300">{label}</span>
        <button
          className={[
            'h-5 w-5 rounded-full border-2 transition-colors',
            selected
              ? 'border-violet-500 bg-violet-500'
              : 'border-gray-600 bg-transparent hover:border-violet-400',
          ].join(' ')}
          onClick={onSelect}
          disabled={!available}
          aria-label={`Wybierz ${type} ${label}`}
          title={available ? `Użyj ${label}` : 'Nie wygenerowano'}
        />
      </div>

      {/* mini waveform */}
      <MiniWaveform peaks={peaks} progress={progress} available={available} />

      {/* playback controls */}
      <div className="flex items-center gap-2">
        <button
          className={[
            'flex h-7 w-7 items-center justify-center rounded-full text-sm',
            'transition-colors disabled:opacity-30',
            isPlaying
              ? 'bg-violet-500 text-white hover:bg-violet-400'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600',
          ].join(' ')}
          onClick={togglePlay}
          disabled={!available}
          aria-label={isPlaying ? 'Stop' : 'Play'}
        >
          {isPlaying ? '⏹' : '▶'}
        </button>

        <div className="flex-1">
          {/* clickable seekbar */}
          <div
            className="relative h-1 cursor-pointer rounded-full bg-gray-700"
            onClick={(e) => {
              const a = audioRef.current;
              if (!a || !duration) return;
              const rect = e.currentTarget.getBoundingClientRect();
              const t = ((e.clientX - rect.left) / rect.width) * duration;
              a.currentTime = Math.max(0, Math.min(duration, t));
            }}
          >
            <div
              className="absolute inset-y-0 left-0 rounded-full bg-violet-500"
              style={{ width: `${progress * 100}%` }}
            />
          </div>
        </div>

        <span className="w-20 text-right font-mono text-[10px] text-gray-500">
          {available && duration !== null
            ? `${fmtTime(curTime)} / ${fmtTime(duration)}`
            : '—'}
        </span>
      </div>

      {!available && (
        <p className="text-center text-[10px] text-gray-600">Nie wygenerowano</p>
      )}
    </div>
  );
}
