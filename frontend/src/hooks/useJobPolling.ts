import { useCallback, useEffect, useRef, useState } from 'react';
import { getJobResult, getJobStatus } from '../api/client';
import type { JobResult, JobStatus } from '../types';

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATES = new Set(['done', 'failed']);

interface UseJobPollingResult {
  status: JobStatus | null;
  result: JobResult | null;
  error: string | null;
}

export function useJobPolling(jobId: string | null): UseJobPollingResult {
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [result, setResult] = useState<JobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeRef = useRef(false);

  const stopPolling = useCallback(() => {
    activeRef.current = false;
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      if (!activeRef.current) return;
      try {
        const s = await getJobStatus(id);
        setStatus(s);

        if (s.status === 'done') {
          stopPolling();
          const r = await getJobResult(id);
          setResult(r);
          return;
        }

        if (s.status === 'failed') {
          stopPolling();
          setError(s.error ?? 'Processing failed');
          return;
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Network error';
        setError(msg);
        stopPolling();
        return;
      }

      if (!TERMINAL_STATES.has(status?.status ?? '')) {
        timerRef.current = setTimeout(() => poll(id), POLL_INTERVAL_MS);
      }
    },
    [status?.status, stopPolling],
  );

  useEffect(() => {
    if (!jobId) return;

    setStatus(null);
    setResult(null);
    setError(null);
    activeRef.current = true;

    poll(jobId);

    return stopPolling;
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  return { status, result, error };
}
